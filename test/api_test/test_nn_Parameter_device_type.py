"""
测试目的：
1. 验证 torch.nn.Parameter.device.type 在 NPU 环境下可正常读取，且返回值始终为字符串。
2. 验证 Parameter 在 CPU / NPU 上直接创建、经过 `.to("npu")` 迁移、放入 Module 后随 `module.to("npu")` 迁移等场景下，`device.type` 的语义一致。
3. 覆盖主要 dtype、requires_grad 取值、空张量边界以及 `device=None` / 非 None 的构造路径，确保不同构造方式下的设备类型属性稳定。
4. 覆盖 `.to()` 的异常入参场景，保证异常使用 pytest.raises 处理。

API 名称：torch.nn.Parameter.device.type

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 直接创建 Parameter | 已覆盖 | 分别在 CPU / NPU 上直接创建 Parameter 并读取 device.type |
| `device=None` / 非 None | 已覆盖 | 通过张量工厂函数分别走默认 CPU 路径和显式 NPU 路径 |
| `.to("npu")` 迁移 | 已覆盖 | 先在 CPU 上创建 Parameter，再迁移到 NPU 后读取 device.type |
| `module.to("npu")` 迁移 | 已覆盖 | Parameter 位于 Module 中，模块迁移后验证参数 device.type |
| `dtype=float32` | 已覆盖 | 覆盖常见浮点类型 |
| `dtype=float16` | 已覆盖 | 覆盖半精度类型 |
| `dtype=int64` | 已覆盖 | 覆盖整型类型，验证非浮点参数场景 |
| `requires_grad=True/False` | 已覆盖 | 浮点参数显式传入 True/False，整型参数走默认 False |
| 空张量边界 | 已覆盖 | 使用空张量构造 Parameter，验证 device.type 仍可正常读取 |
| 异常入参 | 已覆盖 | 非法 `.to()` 传参触发异常，并使用 pytest.raises 校验 |
| 返回值类型 | 已覆盖 | 对 device.type 结果做字符串类型检查 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| device.type 的数值正确性校验 | 该属性仅表达设备类型，本测试仅验证接口语义，不做数值比对 |
| 更多 dtype（如 complex、bfloat16） | 当前已覆盖主要 dtype；其余 dtype 可能受后端支持差异影响，未额外扩展 |
| 多卡/分布式 NPU 场景 | 本测试聚焦单卡 NPU 基础功能，不依赖多卡环境 |
"""

import pytest

import torch
import torch.nn as nn
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.nn.Parameter.device.type 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.nn.Parameter.device.type 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    device = torch.device(f"npu:{torch.npu.current_device()}")
    probe = torch.tensor([1], device=device)
    assert probe.device.type == "npu"
    return device


class SingleParameterModule(nn.Module):
    def __init__(self, dtype: torch.dtype):
        super().__init__()
        requires_grad = dtype.is_floating_point
        data = torch.ones((2, 3), dtype=dtype)
        self.weight = nn.Parameter(data, requires_grad=requires_grad)


def _make_parameter(device, dtype: torch.dtype, requires_grad=None):
    data = torch.ones((2, 3), dtype=dtype, device=device)
    if requires_grad is None:
        requires_grad = dtype.is_floating_point
    return nn.Parameter(data, requires_grad=requires_grad)


def _make_empty_parameter(device, dtype: torch.dtype):
    requires_grad = dtype.is_floating_point
    data = torch.empty((0, 3), dtype=dtype, device=device)
    return nn.Parameter(data, requires_grad=requires_grad)


def _assert_device_type_is(parameter, expected_device_type: str):
    assert isinstance(parameter.device.type, str)
    assert parameter.device.type == expected_device_type


@pytest.mark.parametrize(
    "dtype,requires_grad",
    [
        (torch.float32, None),
        (torch.float32, True),
        (torch.float32, False),
        (torch.float16, None),
        (torch.float16, True),
        (torch.float16, False),
        (torch.int64, None),
    ],
)
def test_parameter_device_type_cpu_parameter_is_cpu_and_str(npu_device, dtype, requires_grad):
    """验证 CPU Parameter 的 device.type 为字符串 'cpu'，并覆盖主要 dtype 与 requires_grad 取值。"""
    param = _make_parameter(torch.device("cpu"), dtype, requires_grad=requires_grad)

    _assert_device_type_is(param, "cpu")


@pytest.mark.parametrize(
    "dtype,requires_grad",
    [
        (torch.float32, None),
        (torch.float32, True),
        (torch.float32, False),
        (torch.float16, None),
        (torch.float16, True),
        (torch.float16, False),
        (torch.int64, None),
    ],
)
def test_parameter_device_type_npu_parameter_is_npu_and_str(npu_device, dtype, requires_grad):
    """验证直接创建的 NPU Parameter 的 device.type 为字符串 'npu'。"""
    param = _make_parameter(npu_device, dtype, requires_grad=requires_grad)

    _assert_device_type_is(param, "npu")


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16, torch.int64])
def test_parameter_device_type_device_none_path_is_cpu_and_str(npu_device, dtype):
    """验证 device=None 的张量工厂默认路径会落到 CPU，Parameter.device.type 仍可正常读取。"""
    param = _make_parameter(None, dtype)

    _assert_device_type_is(param, "cpu")


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16, torch.int64])
def test_parameter_device_type_on_empty_tensor_is_npu_and_str(npu_device, dtype):
    """验证空张量构造的 Parameter 在 NPU 上的 device.type 仍可正常读取。"""
    param = _make_empty_parameter(npu_device, dtype)

    _assert_device_type_is(param, "npu")


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16, torch.int64])
def test_parameter_device_type_after_to_npu_is_npu_and_str(npu_device, dtype):
    """验证 CPU Parameter 经过 `.to("npu")` 后返回对象类型，并确认其 device.type 为 'npu'。"""
    param = _make_parameter(torch.device("cpu"), dtype)
    moved = param.to(npu_device)

    assert isinstance(param, nn.Parameter)
    assert not isinstance(moved, nn.Parameter)
    _assert_device_type_is(moved, "npu")


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16, torch.int64])
def test_parameter_device_type_in_module_after_module_to_npu(npu_device, dtype):
    """验证 Parameter 位于 Module 中时，`module.to("npu")` 之后参数 device.type 为 'npu'。"""
    module = SingleParameterModule(dtype=dtype)

    _assert_device_type_is(module.weight, "cpu")

    module = module.to(npu_device)

    _assert_device_type_is(module.weight, "npu")


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16])
@pytest.mark.parametrize("requires_grad", [True, False])
def test_parameter_device_type_explicit_requires_grad_on_npu(npu_device, dtype, requires_grad):
    """验证浮点 Parameter 显式传入 requires_grad=True/False 时，device.type 仍为 'npu'。"""
    param = _make_parameter(npu_device, dtype, requires_grad=requires_grad)

    _assert_device_type_is(param, "npu")


def test_parameter_device_type_invalid_to_device_raises(npu_device):
    """验证 `.to()` 的非法 device 传参时会抛出异常。"""
    param = _make_parameter(npu_device, torch.float32)

    with pytest.raises(RuntimeError, match="device type|device string|Expected one of"):
        _ = param.to("invalid_device")
