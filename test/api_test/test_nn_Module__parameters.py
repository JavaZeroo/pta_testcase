"""
测试目的：
1. 验证 `torch.nn.Module._parameters` 在 NPU 环境中始终表现为模块直接参数的容器，且容器类型为 `dict`。
2. 覆盖参数“传入/不传入”对应的模块状态变化：新建模块为空、`Parameter` 赋值后自动写入、`register_parameter(..., None)` 占位、`delattr` 删除后同步移除。
3. 覆盖主要类型与主要分支：`Parameter`、`None`、普通 `Tensor`、`Linear` 默认参数、`.to("npu")` 迁移后的设备状态。
4. 覆盖异常场景：非法参数类型、非法参数名，均使用 `pytest.raises` 断言。

API 名称：torch.nn.Module._parameters

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 默认状态 | 已覆盖 | 新建 `nn.Module()` 时 `_parameters` 为空 `dict` |
| 容器类型 | 已覆盖 | 验证 `_parameters` 满足 `dict` 的类型检查 |
| `Parameter` 赋值 | 已覆盖 | 通过 `__setattr__` 赋值 `nn.Parameter` 后，参数会出现在 `_parameters` |
| `register_parameter(..., Parameter)` | 已覆盖 | 验证显式注册参数后写入 `_parameters` |
| `register_parameter(..., None)` | 已覆盖 | 验证名称会写入 `_parameters`，值为 `None` |
| 普通 `Tensor` 赋值 | 已覆盖 | 验证普通 `Tensor` 不会被当作参数写入 `_parameters` |
| 删除参数 | 已覆盖 | 验证 `delattr` 后 `_parameters` 中对应键同步移除 |
| 键类型 | 已覆盖 | 验证 `_parameters` 的键均为字符串 |
| 值类型 | 已覆盖 | 验证 `_parameters` 的值为 `Parameter` 或 `None` |
| `.to("npu")` 迁移 | 已覆盖 | 验证迁移后 `_parameters` 中非空参数均位于 NPU |
| `Linear` 标准参数 | 已覆盖 | 验证 `weight/bias` 均在 `_parameters` 中 |
| 异常类型 | 已覆盖 | 非法参数类型、非法参数名均使用 `pytest.raises` 断言 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 参数数值正确性 | 本测试聚焦 `_parameters` 容器语义、类型与设备属性，不校验具体数值 |
| 多卡/分布式迁移策略 | 当前用例仅验证单卡 NPU 基础行为，不依赖多卡环境 |
| 所有内部边界组合 | 已覆盖核心路径与主要异常分支，未穷举全部内部实现细节 |
"""

import pytest

import torch
import torch.nn as nn
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Module._parameters 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Module._parameters 测试。")


class _ParameterHolder(nn.Module):
    def __init__(self):
        super().__init__()
        self.direct_weight = nn.Parameter(torch.randn(2, 3))
        self.register_parameter("optional_bias", None)


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    device = torch.device("npu:0")
    probe = torch.tensor([1], device=device)
    assert probe.device.type == "npu"
    assert probe.device.index == 0
    return device


@pytest.fixture()
def empty_module_npu(npu_device):
    module = nn.Module().to(npu_device)
    return module


@pytest.fixture()
def parameter_holder_npu(npu_device):
    module = _ParameterHolder().to(npu_device)
    return module


@pytest.fixture()
def linear_module_npu(npu_device):
    module = nn.Linear(4, 2).to(npu_device)
    return module


def test_module_parameters_default_is_empty_dict(empty_module_npu):
    """验证新建模块的 `_parameters` 默认为空 `dict`，且容器类型符合预期。"""
    params = empty_module_npu._parameters

    assert params == {}
    assert isinstance(params, dict)
    assert len(params) == 0
    assert list(params.keys()) == []
    assert list(params.values()) == []


def test_module_parameters_after_parameter_assignment_and_register_none(parameter_holder_npu):
    """验证 `Parameter` 赋值与 `register_parameter(..., None)` 都会写入 `_parameters`。"""
    params = parameter_holder_npu._parameters

    assert list(params.keys()) == ["direct_weight", "optional_bias"]
    assert all(isinstance(name, str) for name in params.keys())
    assert isinstance(params["direct_weight"], nn.Parameter)
    assert params["direct_weight"] is parameter_holder_npu.direct_weight
    assert params["optional_bias"] is None
    assert isinstance(parameter_holder_npu.direct_weight, nn.Parameter)
    assert parameter_holder_npu.direct_weight.device.type == "npu"
    assert parameter_holder_npu.direct_weight.device.index == 0


def test_module_parameters_assignment_after_init_is_tracked(npu_device):
    """验证模块初始化后再赋值 `nn.Parameter`，也会通过 `__setattr__` 写入 `_parameters`。"""
    module = nn.Module().to(npu_device)
    module.new_param = nn.Parameter(torch.ones(2, device=npu_device))

    assert "new_param" in module._parameters
    assert isinstance(module._parameters["new_param"], nn.Parameter)
    assert module._parameters["new_param"].device.type == "npu"
    assert module._parameters["new_param"].device.index == 0
    assert module.new_param is module._parameters["new_param"]


def test_module_parameters_plain_tensor_assignment_not_tracked(npu_device):
    """验证普通 `Tensor` 赋值不会被写入 `_parameters`，避免把非参数误判为参数。"""
    module = nn.Module().to(npu_device)
    plain_tensor = torch.tensor([3.0], device=npu_device)
    module.plain_tensor = plain_tensor

    assert "plain_tensor" not in module._parameters
    assert module.plain_tensor is plain_tensor


def test_module_parameters_register_parameter_explicit_parameter_and_delete(npu_device):
    """验证显式注册 `Parameter` 后可进入 `_parameters`，且删除后会同步移除。"""
    module = nn.Module().to(npu_device)
    parameter = nn.Parameter(torch.full((2,), 1.0, device=npu_device))

    module.register_parameter("registered_param", parameter)
    assert "registered_param" in module._parameters
    assert module._parameters["registered_param"] is parameter
    assert module._parameters["registered_param"].device.type == "npu"

    del module.registered_param
    assert "registered_param" not in module._parameters
    assert "registered_param" not in module.__dict__


def test_module_parameters_after_to_npu_parameters_are_on_npu(parameter_holder_npu):
    """验证模块 `.to("npu")` 后，`_parameters` 中非空参数均位于 NPU。"""
    params = parameter_holder_npu._parameters

    assert list(params.keys()) == ["direct_weight", "optional_bias"]
    for name, value in params.items():
        assert isinstance(name, str)
        assert value is None or isinstance(value, nn.Parameter)
        if value is not None:
            assert value.device.type == "npu"
            assert value.device.index == 0


def test_module_parameters_linear_has_weight_and_bias_in_parameters(linear_module_npu):
    """验证 `Linear` 模块的 `weight/bias` 会出现在 `_parameters` 中，且位于 NPU。"""
    params = linear_module_npu._parameters

    assert list(params.keys()) == ["weight", "bias"]
    assert isinstance(params["weight"], nn.Parameter)
    assert isinstance(params["bias"], nn.Parameter)
    assert params["weight"].device.type == "npu"
    assert params["bias"].device.type == "npu"
    assert params["weight"].device.index == 0
    assert params["bias"].device.index == 0


@pytest.mark.parametrize(
    "name, value_kind, expected_exception",
    [
        (123, "parameter", TypeError),
        ("bad_param", "tensor", TypeError),
        ("", "parameter", KeyError),
        ("bad.name", "parameter", KeyError),
    ],
)
def test_module_register_parameter_invalid_input_raises(npu_device, name, value_kind, expected_exception):
    """验证 `register_parameter` 的非法参数名/非法参数类型会抛出对应异常。"""
    module = nn.Module().to(npu_device)

    if value_kind == "parameter":
        value = nn.Parameter(torch.tensor([1.0], device=npu_device))
    else:
        value = torch.tensor([1.0], device=npu_device)

    with pytest.raises(expected_exception):
        module.register_parameter(name, value)
