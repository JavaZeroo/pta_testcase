"""
测试目的：
1. 验证 torch.nn.Parameter.device 作为 Tensor 继承属性，在 NPU 环境中可正常返回 torch.device 对象。
2. 覆盖默认 CPU 参数、显式传入 requires_grad、通过 .to("npu") / module.to("npu") 迁移后的参数、不同 dtype、只读属性异常等关键场景。
3. 验证返回设备的 type / index 属性以及 torch.device 类型判断在 NPU 上符合预期。
4. 该 API 本身为属性访问，无显式入参，因此主要覆盖参数对象状态与异常访问路径。

API 名称：torch.nn.Parameter.device

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 属性访问（无显式入参） | 已覆盖 | 直接读取 `.device`，无需传参 |
| 默认设备（CPU） | 已覆盖 | Parameter 默认创建在 CPU，device.type 为 cpu |
| 显式 requires_grad | 已覆盖 | 默认不传与显式传入 False 两种情况均覆盖 |
| 迁移到 NPU | 已覆盖 | `Parameter.to(...)` 迁移后对象的 device 以及 `module.to("npu")` 场景均覆盖 |
| device.type | 已覆盖 | 验证 CPU / NPU 的 type 取值 |
| device.index | 已覆盖 | 验证 NPU 场景下 index 与当前设备一致 |
| 返回值类型 | 已覆盖 | 验证返回值为 `torch.device` 实例 |
| 不同 dtype | 已覆盖 | 覆盖 float16 / float32 / int32 |
| nn.Module 内 Parameter | 已覆盖 | 验证 module.to("npu") 后内部参数设备属性 |
| 只读属性异常 | 已覆盖 | 对 `device` 赋值时使用 pytest.raises 验证异常 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值正确性 | `.device` 只返回设备信息，不涉及数值计算，本测试不做数值比对 |
| 多卡 / 跨卡设备切换 | 当前用例聚焦单卡 NPU 基本行为，不依赖多卡环境 |
| 非当前卡号的 NPU 场景 | 当前用例聚焦当前可用 NPU 设备的基础行为，不额外切换到其他卡 |
| 其他异常写法（如对内部属性强行篡改） | 该属性为只读，已用赋值异常覆盖主要异常路径，未逐一枚举所有非法访问方式 |
"""

import pytest

import torch
import torch.nn as nn
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Parameter.device 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Parameter.device 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    current_index = torch.npu.current_device()
    device = torch.device(f"npu:{current_index}")
    probe = torch.tensor([1], device=device)
    assert probe.device.type == "npu"
    assert probe.device.index == current_index
    return device


def _make_parameter(device, dtype=torch.float32):
    if dtype in (torch.int32, torch.int64, torch.int16, torch.int8, torch.uint8, torch.bool):
        return nn.Parameter(torch.ones((2, 3), device=device, dtype=dtype), requires_grad=False)
    return nn.Parameter(torch.ones((2, 3), device=device, dtype=dtype))


def test_parameter_device_default_cpu_is_torch_device(npu_device):
    """验证默认创建的 Parameter 位于 CPU，且 device 返回 torch.device 对象。"""
    param = nn.Parameter(torch.ones((2, 3)))

    assert isinstance(param.device, torch.device)
    assert param.device.type == "cpu"
    assert param.device.index is None


@pytest.mark.parametrize(
    "dtype, requires_grad",
    [
        (torch.float16, True),
        (torch.float32, True),
        (torch.int32, False),
    ],
)
def test_parameter_device_on_npu_for_various_dtypes(npu_device, dtype, requires_grad):
    """验证不同 dtype 的 Parameter 在 NPU 上读取 device 时均返回正确的设备对象。"""
    param = nn.Parameter(
        torch.ones((2, 3), device=npu_device, dtype=dtype),
        requires_grad=requires_grad,
    )

    assert isinstance(param.device, torch.device)
    assert param.device.type == "npu"
    assert param.device.index == npu_device.index
    assert param.device == npu_device


def test_parameter_device_after_to_npu_keeps_npu_device(npu_device):
    """验证对象经 .to('npu') 后返回 Tensor，且其 device 信息正确。"""
    param = nn.Parameter(torch.ones((2, 3)))
    moved = param.to(npu_device)

    assert isinstance(moved.device, torch.device)
    assert moved.device.type == "npu"
    assert moved.device.index == npu_device.index


def test_parameter_device_inside_module_after_module_to_npu(npu_device):
    """验证 nn.Module.to('npu') 后，模块内部 Parameter 的 device 为 NPU。"""
    module = nn.Linear(4, 2)
    module = module.to(npu_device)

    weight = module.weight
    bias = module.bias

    assert isinstance(weight.device, torch.device)
    assert isinstance(bias.device, torch.device)
    assert weight.device.type == "npu"
    assert bias.device.type == "npu"
    assert weight.device.index == npu_device.index
    assert bias.device.index == npu_device.index


def test_parameter_device_read_only_assignment_raises(npu_device):
    """验证 device 为只读属性，对其赋值时会抛出异常。"""
    param = _make_parameter(npu_device, dtype=torch.float32)

    with pytest.raises(AttributeError):
        param.device = npu_device
