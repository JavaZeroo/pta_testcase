"""
测试目的：
1. 验证 torch.nn.Parameter.dtype 作为继承自 Tensor 的只读属性，在 NPU 上可正常读取，且返回值类型为 torch.dtype。
2. 覆盖 Parameter 由默认 dtype 与显式 dtype 创建后的 dtype 行为，重点验证主要常用 dtype 在 NPU 上可读。
3. 验证 Parameter 注册到 nn.Module 后 dtype 仍保持一致，并确认对象实际位于 NPU。
4. 覆盖异常场景：对 dtype 属性进行非法赋值、以及对 Parameter 调用非法 .to(dtype=...) 时抛出异常。

API 名称：torch.nn.Parameter.dtype

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| dtype 参数不传 | 已覆盖 | 使用 torch.ones 默认浮点 dtype 创建 Parameter，验证默认 float32 |
| dtype 参数显式传入 | 已覆盖 | 覆盖 float16 / float64 / int32 / int64 / bool |
| requires_grad 参数不传 | 已覆盖 | 直接使用 nn.Parameter(data) 的默认行为 |
| requires_grad 显式传入非 None | 已覆盖 | 对整数/布尔 dtype 显式传入 False |
| 传入显式 None dtype | 已覆盖 | 使用 torch.ones(..., dtype=None) 验证会回退到默认 dtype |
| dtype 返回类型 | 已覆盖 | 验证 Parameter.dtype 是 torch.dtype 实例 |
| dtype 只读属性 | 已覆盖 | 验证对 dtype 直接赋值会抛出异常 |
| .to(dtype) 变更 | 已覆盖 | 验证 Parameter 经过 .to(dtype=...) 后返回 Tensor 的 dtype 改变且仍在 NPU |
| Parameter in Module | 已覆盖 | 验证注册到 nn.Module 后 dtype 仍保持一致 |
| NPU 设备 | 已覆盖 | 验证 Parameter 创建、读取 dtype、Module 持有均在 npu:0 上 |
| 异常场景 | 已覆盖 | 验证非法 dtype 入参调用 .to 时抛出异常 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值正确性 | 本测试聚焦 dtype 元数据与设备行为，不做张量内容数值校验 |
| 所有可能 dtype 枚举 | 仅覆盖主要常用 dtype，其他 dtype 不属于当前 API 的核心覆盖范围 |
| 多卡/分布式场景 | 当前仅验证单卡 NPU 基础行为，不依赖多卡环境 |
| 与优化器、反向传播联动的上层训练行为 | 本文件仅覆盖 Parameter.dtype 属性及其基础使用场景，不扩展到训练框架集成 |
"""

import pytest

import torch
import torch_npu  # noqa: F401
import torch.nn as nn


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.nn.Parameter.dtype 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.nn.Parameter.dtype 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device(f"npu:{torch.npu.current_device()}")


def _make_parameter(npu_device, dtype=None, requires_grad=None):
    """创建位于 NPU 上的 Parameter；仅对后端明确不支持的 dtype 进行跳过。"""
    try:
        if dtype is None:
            data = torch.ones((2, 2), device=npu_device)
        elif dtype is torch.bool:
            data = torch.tensor([[True, False], [False, True]], device=npu_device, dtype=dtype)
        else:
            data = torch.ones((2, 2), device=npu_device, dtype=dtype)
    except (RuntimeError, TypeError, ValueError) as exc:
        msg = str(exc).lower()
        if any(key in msg for key in ("not supported", "unsupported", "not implemented", "does not support")):
            pytest.skip(f"当前 NPU 后端不支持 dtype={dtype} 的 Parameter 创建：{exc}")
        raise

    kwargs = {}
    if requires_grad is not None:
        kwargs["requires_grad"] = requires_grad
    return nn.Parameter(data, **kwargs)


def test_parameter_dtype_default_float32_and_isinstance(npu_device):
    """验证默认 dtype 不显式传入时，Parameter.dtype 为 float32 且类型为 torch.dtype。"""
    old_default_dtype = torch.get_default_dtype()
    try:
        torch.set_default_dtype(torch.float32)
        param = _make_parameter(npu_device)
    finally:
        torch.set_default_dtype(old_default_dtype)

    assert param.device.type == "npu"
    assert param.device.index == torch.npu.current_device()
    assert isinstance(param.dtype, torch.dtype)
    assert param.dtype == torch.float32


@pytest.mark.parametrize(
    "dtype, requires_grad",
    [
        (torch.float16, None),
        (torch.float64, None),
        (torch.int32, False),
        (torch.int64, False),
        (torch.bool, False),
    ],
)
def test_parameter_dtype_explicit_dtypes_on_npu(npu_device, dtype, requires_grad):
    """验证显式传入主要 dtype 时，Parameter.dtype 与传入 dtype 一致。"""
    param = _make_parameter(npu_device, dtype=dtype, requires_grad=requires_grad)

    assert param.device.type == "npu"
    assert param.device.index == torch.npu.current_device()
    assert isinstance(param.dtype, torch.dtype)
    assert param.dtype == dtype


def test_parameter_dtype_after_to_dtype_change_on_npu(npu_device):
    """验证 Parameter 经过 .to(dtype=...) 后返回 Tensor，且 dtype 会改变并仍位于 NPU。"""
    param = _make_parameter(npu_device, dtype=torch.float32)

    converted = param.to(dtype=torch.float16)

    assert isinstance(converted, torch.Tensor)
    assert not isinstance(converted, nn.Parameter)
    assert isinstance(converted.dtype, torch.dtype)
    assert converted.device.type == "npu"
    assert converted.device.index == torch.npu.current_device()
    assert converted.dtype == torch.float16
    assert param.dtype == torch.float32


def test_parameter_dtype_preserved_in_module_on_npu(npu_device):
    """验证 Parameter 注册到 nn.Module 后，其 dtype 与 NPU 设备属性保持不变。"""

    class _ModuleWithParameter(nn.Module):
        def __init__(self, weight):
            super().__init__()
            self.weight = weight

    weight = _make_parameter(npu_device, dtype=torch.float16)
    module = _ModuleWithParameter(weight)

    assert "weight" in dict(module.named_parameters())
    assert module.weight.device.type == "npu"
    assert module.weight.device.index == torch.npu.current_device()
    assert isinstance(module.weight.dtype, torch.dtype)
    assert module.weight.dtype == torch.float16


def test_parameter_dtype_invalid_to_dtype_raises(npu_device):
    """验证非法 dtype 入参调用 .to(dtype=...) 时抛出异常。"""
    param = _make_parameter(npu_device, dtype=torch.float32)

    with pytest.raises((TypeError, RuntimeError)):
        param.to(dtype="float32")


def test_parameter_dtype_readonly_assignment_raises(npu_device):
    """验证 dtype 是只读属性，对其直接赋值会抛出异常。"""
    param = _make_parameter(npu_device, dtype=torch.float32)

    with pytest.raises(AttributeError):
        param.dtype = torch.float16


def test_parameter_dtype_from_explicit_none_dtype_uses_default_dtype(npu_device):
    """验证工厂函数显式传入 dtype=None 时，Parameter.dtype 回退到默认 dtype。"""
    old_default_dtype = torch.get_default_dtype()
    try:
        torch.set_default_dtype(torch.float32)
        data = torch.ones((2, 2), device=npu_device, dtype=None)
        param = nn.Parameter(data)
    finally:
        torch.set_default_dtype(old_default_dtype)

    assert param.device.type == "npu"
    assert param.device.index == torch.npu.current_device()
    assert isinstance(param.dtype, torch.dtype)
    assert param.dtype == torch.float32
