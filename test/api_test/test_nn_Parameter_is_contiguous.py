"""
测试目的：
1. 验证 torch.nn.Parameter.is_contiguous 在 NPU 上可正常调用，且返回值类型为 bool。
2. 覆盖默认参数、显式 memory_format 参数、None/非 None 参数、主要 memory_format 枚举值、连续/非连续参数等场景。
3. 验证 Parameter 必须创建在 NPU 上，并检查不同 memory_format 下的基础布尔行为与异常行为。

API 名称：torch.nn.Parameter.is_contiguous

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 参数传/不传 | 已覆盖 | 默认不传、显式传入 memory_format |
| memory_format | 已覆盖 | torch.contiguous_format / torch.channels_last / torch.channels_last_3d / torch.preserve_format / None / 非法整数 |
| tensor 布局 | 已覆盖 | contiguous 参数、channels_last 参数、transpose 后的非连续参数 |
| 参数类型 | 已覆盖 | torch.nn.Parameter，且参数位于 NPU |
| 返回类型 | 已覆盖 | 校验返回值为 bool |
| 异常场景 | 已覆盖 | memory_format=None、memory_format=0 时使用 pytest.raises 捕获 TypeError |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值正确性 | 该 API 仅返回布尔值，测试聚焦连续性判定与接口行为，不做数值正确性校验 |
| 多卡/跨卡一致性 | 当前用例仅验证单卡 NPU 基础功能，不依赖多 NPU 环境 |
| 非法字符串/自定义对象等更多 memory_format 异常类型 | 已通过 None、整数异常场景覆盖主要非法路径，避免重复测试同类错误分支 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.nn.Parameter.is_contiguous 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.nn.Parameter.is_contiguous 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device("npu:0")


def _make_contiguous_parameter(device):
    tensor = torch.randn((2, 3, 4, 5), device=device, dtype=torch.float32)
    param = torch.nn.Parameter(tensor)
    assert isinstance(param, torch.nn.Parameter)
    assert param.device.type == "npu"
    return param


def _make_channels_last_parameter(device):
    # 当前 NPU 后端不支持直接对 NPU Tensor 施加 channels_last 变换，因此先在 CPU 侧构造，
    # 再迁移到 NPU，保证测试仍然在 NPU 上执行。
    tensor = torch.randn((2, 3, 4, 5), dtype=torch.float32).to(
        memory_format=torch.channels_last
    ).to(device)
    param = torch.nn.Parameter(tensor)
    assert isinstance(param, torch.nn.Parameter)
    assert param.device.type == "npu"
    return param


def _make_non_contiguous_parameter(device):
    tensor = torch.arange(24, device=device, dtype=torch.float32).reshape(2, 3, 4)
    param = torch.nn.Parameter(tensor.transpose(0, 1))
    assert isinstance(param, torch.nn.Parameter)
    assert param.device.type == "npu"
    return param


def _make_channels_last_3d_parameter(device):
    # 当前 NPU 后端不支持直接对 NPU Tensor 施加 channels_last_3d 变换，因此先在 CPU 侧构造，
    # 再迁移到 NPU，保证测试仍然在 NPU 上执行。
    tensor = torch.randn((2, 3, 4, 5, 6), dtype=torch.float32).to(
        memory_format=torch.channels_last_3d
    ).to(device)
    param = torch.nn.Parameter(tensor)
    assert isinstance(param, torch.nn.Parameter)
    assert param.device.type == "npu"
    return param


def test_parameter_is_contiguous_default_and_explicit_contiguous_modes(npu_device):
    """验证连续 Parameter 在默认/显式 contiguous_format/preserve_format 下的返回类型与行为。"""
    param = _make_contiguous_parameter(npu_device)

    out_default = param.is_contiguous()
    out_contiguous = param.is_contiguous(memory_format=torch.contiguous_format)
    out_preserve = param.is_contiguous(memory_format=torch.preserve_format)

    assert type(out_default) is bool
    assert type(out_contiguous) is bool
    assert type(out_preserve) is bool
    assert out_default is True
    assert out_contiguous is True
    assert out_preserve is True


def test_parameter_is_contiguous_channels_last_parameter(npu_device):
    """验证 channels_last 布局 Parameter 在不同 memory_format 下的返回类型与行为。"""
    param = _make_channels_last_parameter(npu_device)

    out_default = param.is_contiguous()
    out_channels_last = param.is_contiguous(memory_format=torch.channels_last)
    out_contiguous = param.is_contiguous(memory_format=torch.contiguous_format)
    out_preserve = param.is_contiguous(memory_format=torch.preserve_format)

    assert type(out_default) is bool
    assert type(out_channels_last) is bool
    assert type(out_contiguous) is bool
    assert type(out_preserve) is bool
    assert out_default is False
    assert out_channels_last is True
    assert out_contiguous is False
    assert out_preserve is False


def test_parameter_is_contiguous_channels_last_3d_parameter(npu_device):
    """验证 channels_last_3d 布局 Parameter 在不同 memory_format 下的返回类型与行为。"""
    param = _make_channels_last_3d_parameter(npu_device)

    out_default = param.is_contiguous()
    out_channels_last_3d = param.is_contiguous(memory_format=torch.channels_last_3d)
    out_contiguous = param.is_contiguous(memory_format=torch.contiguous_format)
    out_preserve = param.is_contiguous(memory_format=torch.preserve_format)

    assert type(out_default) is bool
    assert type(out_channels_last_3d) is bool
    assert type(out_contiguous) is bool
    assert type(out_preserve) is bool
    assert out_default is False
    assert out_channels_last_3d is True
    assert out_contiguous is False
    assert out_preserve is False


def test_parameter_is_contiguous_non_contiguous_after_transpose(npu_device):
    """验证 transpose 之后的非连续 Parameter 在默认/显式 contiguous_format 下的行为。"""
    param = _make_non_contiguous_parameter(npu_device)

    out_default = param.is_contiguous()
    out_contiguous = param.is_contiguous(memory_format=torch.contiguous_format)

    assert type(out_default) is bool
    assert type(out_contiguous) is bool
    assert out_default is False
    assert out_contiguous is False


@pytest.mark.parametrize("memory_format", [None, 0])
def test_parameter_is_contiguous_invalid_memory_format_raises(npu_device, memory_format):
    """验证非法 memory_format 入参时通过 pytest.raises 抛出 TypeError。"""
    param = _make_contiguous_parameter(npu_device)

    with pytest.raises(TypeError):
        param.is_contiguous(memory_format=memory_format)
