"""
测试目的：
1. 验证 torch.nn.Module.__setattr__ 在 NPU 场景下对 Parameter、子模块、普通值、buffer 和 None 的自动注册、覆盖、清理与置空行为。
2. 覆盖参数传入与不传、None/非 None、主要类型、已有属性覆盖、NPU Parameter 赋值，以及非法覆盖/未初始化场景下的异常。
3. 本测试聚焦属性注册、内部容器更新和设备行为，不做具体数值正确性校验。

API 名称：torch.nn.Module.__setattr__(name, value)

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 参数传入（name/value） | 已覆盖 | 直接调用与缺参调用均覆盖 |
| value 为 Parameter | 已覆盖 | 直接 setattr，自动进入 _parameters |
| value 为 Module | 已覆盖 | 直接 setattr，自动进入 _modules |
| value 为普通值 | 已覆盖 | 进入 __dict__，不进入 _parameters/_modules/_buffers |
| value 为 buffer | 已覆盖 | 先 register_buffer，再用 setattr 覆盖同名条目，并覆盖 None/非法类型分支 |
| value 为 None | 已覆盖 | 参数/子模块/buffer 条目置空，后续遍历不再返回该项 |
| NPU Parameter | 已覆盖 | Parameter 在 npu:0 上创建并赋值 |
| 覆盖已有 Parameter | 已覆盖 | 用新的 Parameter 替换旧条目 |
| 覆盖已有 Module | 已覆盖 | 先写入普通值再改写为 Module，验证容器迁移 |
| 非法覆盖异常 | 已覆盖 | 用普通 Tensor 覆盖已有 Parameter / Module 时抛出 TypeError |
| 未初始化 Module | 已覆盖 | 使用 object.__new__ 构造未初始化对象并触发 AttributeError |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 参数数值正确性 | __setattr__ 只负责注册与属性管理，不涉及数值计算 |
| 多 NPU 卡或分布式场景 | 当前仅验证单卡 npu:0 的基础行为 |
| 更复杂的嵌套共享注册冲突 | 已覆盖核心注册、覆盖与迁移路径，未进一步展开更复杂组合 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Module.__setattr__ 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Module.__setattr__ 测试。")


@pytest.fixture()
def npu_device():
    _require_npu()
    device = torch.device("npu:0")
    probe = torch.tensor([0], device=device)
    assert probe.device.type == "npu"
    return device


def test_setattr_parameter_registers_in_parameters_and_on_npu(npu_device):
    """验证 Parameter 赋值会自动注册到 _parameters，并保持 NPU 设备属性。"""
    module = torch.nn.Module()
    param = torch.nn.Parameter(torch.ones(2, device=npu_device))

    module.foo = param

    assert module.foo is param
    assert isinstance(module.foo, torch.nn.Parameter)
    assert "foo" in module._parameters
    assert module._parameters["foo"] is param
    assert "foo" not in module._modules
    assert "foo" not in module.__dict__
    assert module.foo.device.type == "npu"
    assert module.foo.device.index == 0


def test_setattr_module_registers_in_modules(npu_device):
    """验证 Module 赋值会自动注册到 _modules，并保留子模块的 NPU 参数。"""
    module = torch.nn.Module()
    child = torch.nn.Linear(2, 3).to(npu_device)

    module.child = child

    assert module.child is child
    assert isinstance(module.child, torch.nn.Module)
    assert "child" in module._modules
    assert module._modules["child"] is child
    assert "child" not in module._parameters
    assert "child" not in module.__dict__

    child_params = list(module.child.parameters())
    assert child_params
    assert all(param.device.type == "npu" for param in child_params)
    assert all(param.device.index == 0 for param in child_params)


def test_setattr_regular_value_goes_to_dict(npu_device):
    """验证普通值赋值会进入 __dict__，而不会进入参数或子模块注册表。"""
    module = torch.nn.Module()
    regular_value = {"kind": "plain", "index": 1}

    module.meta = regular_value

    assert module.meta == regular_value
    assert module.__dict__["meta"] == regular_value
    assert "meta" not in module._parameters
    assert "meta" not in module._modules
    assert "meta" not in module._buffers


def test_setattr_buffer_then_overwrite_updates_buffer_entry(npu_device):
    """验证 register_buffer 后再 setattr 同名属性时，会更新 _buffers 中的条目。"""
    module = torch.nn.Module()
    original = torch.tensor([1.0], device=npu_device)
    replacement = torch.tensor([2.0], device=npu_device)

    module.register_buffer("buf", original)
    assert "buf" in module._buffers
    assert module._buffers["buf"] is original

    module.buf = replacement

    assert module.buf is replacement
    assert "buf" in module._buffers
    assert module._buffers["buf"] is replacement
    assert "buf" not in module._parameters
    assert module.buf.device.type == "npu"


def test_setattr_none_clears_module_registration(npu_device):
    """验证给已有子模块名赋 None 后，子模块不再参与 named_children 遍历。"""
    module = torch.nn.Module()
    module.child = torch.nn.Linear(2, 3).to(npu_device)
    assert "child" in module._modules

    module.child = None

    assert module.child is None
    assert "child" in module._modules
    assert module._modules["child"] is None
    assert list(module.named_children()) == []


def test_setattr_none_clears_parameter_registration(npu_device):
    """验证给已有参数名赋 None 后，参数不再参与 named_parameters 遍历。"""
    module = torch.nn.Module()
    module.weight = torch.nn.Parameter(torch.ones(1, device=npu_device))
    assert "weight" in module._parameters

    module.weight = None

    assert module.weight is None
    assert "weight" in module._parameters
    assert module._parameters["weight"] is None
    assert list(module.named_parameters()) == []


def test_setattr_none_clears_buffer_registration(npu_device):
    """验证给已有 buffer 名赋 None 后，buffer 不再参与 named_buffers 遍历。"""
    module = torch.nn.Module()
    module.register_buffer("buf", torch.tensor([1.0], device=npu_device))
    assert "buf" in module._buffers

    module.buf = None

    assert module.buf is None
    assert "buf" in module._buffers
    assert module._buffers["buf"] is None
    assert list(module.named_buffers()) == []


def test_setattr_npu_parameter_assignment_and_overwrite_existing_parameter(npu_device):
    """验证 NPU Parameter 赋值，以及同名 Parameter 的覆盖更新行为。"""
    module = torch.nn.Module()
    first = torch.nn.Parameter(torch.ones(2, device=npu_device))
    second = torch.nn.Parameter(torch.ones(2, device=npu_device))

    module.weight = first
    module.weight = second

    assert module.weight is second
    assert module._parameters["weight"] is second
    assert module.weight.device.type == "npu"
    assert module.weight.device.index == 0
    assert len(list(module.named_parameters())) == 1


def test_setattr_overwrite_existing_parameter_with_tensor_raises(npu_device):
    """验证用普通 Tensor 覆盖已有 Parameter 时会抛出 TypeError。"""
    module = torch.nn.Module()
    module.weight = torch.nn.Parameter(torch.ones(1, device=npu_device))

    with pytest.raises(TypeError):
        module.weight = torch.tensor([2.0], device=npu_device)


def test_setattr_overwrite_existing_module_with_tensor_raises(npu_device):
    """验证用普通 Tensor 覆盖已有 Module 时会抛出 TypeError。"""
    module = torch.nn.Module()
    module.child = torch.nn.Linear(2, 3).to(npu_device)

    with pytest.raises(TypeError):
        module.child = torch.tensor([2.0], device=npu_device)


def test_setattr_overwrite_existing_buffer_with_invalid_type_raises(npu_device):
    """验证用非 Tensor/None 类型覆盖已有 buffer 时会抛出 TypeError。"""
    module = torch.nn.Module()
    module.register_buffer("buf", torch.tensor([1.0], device=npu_device))

    with pytest.raises(TypeError):
        module.buf = "invalid"


def test_setattr_missing_value_argument_raises_type_error(npu_device):
    """验证直接调用 __setattr__ 时缺少 value 参数会抛出 TypeError。"""
    module = torch.nn.Module()

    with pytest.raises(TypeError):
        torch.nn.Module.__setattr__(module, "only_name")


def test_setattr_before_module_init_for_parameter_and_module_raises_attribute_error(
    npu_device,
):
    """验证未执行 Module.__init__ 时，赋值 Parameter/Module 会抛出 AttributeError。"""
    uninitialized = object.__new__(torch.nn.Module)

    with pytest.raises(AttributeError):
        torch.nn.Module.__setattr__(
            uninitialized,
            "weight",
            torch.nn.Parameter(torch.ones(1, device=npu_device)),
        )

    with pytest.raises(AttributeError):
        torch.nn.Module.__setattr__(
            uninitialized, "child", torch.nn.Linear(2, 3).to(npu_device)
        )


def test_setattr_parameter_replaces_buffer_entry_on_npu(npu_device):
    """验证已有 buffer 名称被 Parameter 覆盖时，会从 _buffers 迁移到 _parameters。"""
    module = torch.nn.Module()
    module.register_buffer("slot", torch.tensor([1.0], device=npu_device))
    param = torch.nn.Parameter(torch.ones(1, device=npu_device))

    module.slot = param

    assert module.slot is param
    assert "slot" in module._parameters
    assert module._parameters["slot"] is param
    assert "slot" not in module._buffers
    assert "slot" not in module._modules


def test_setattr_module_replaces_regular_value_entry_on_npu(npu_device):
    """验证普通值同名位置被 Module 覆盖时，会从 __dict__ 迁移到 _modules。"""
    module = torch.nn.Module()
    module.slot = "placeholder"
    child = torch.nn.Linear(2, 3).to(npu_device)

    module.slot = child

    assert module.slot is child
    assert "slot" in module._modules
    assert module._modules["slot"] is child
    assert "slot" not in module.__dict__
    assert "slot" not in module._buffers
