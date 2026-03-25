"""
测试目的：
1. 验证 torch.nn.Parameter.stride 在 NPU 上可调用，且无参调用与显式 dim=None 都返回 tuple。
2. 验证传入 dim 参数时返回 int，覆盖正向索引、负向索引、越界索引以及非整数类型异常。
3. 验证连续、非连续以及 0 维 / 1 维 / 2 维 / 3 维 Parameter 的接口行为一致性。

API 名称：torch.nn.Parameter.stride

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| dim 传参与不传 | 已覆盖 | 无参调用、显式 dim=None、显式 int dim |
| dim 取值类型 | 已覆盖 | int、None、float、str |
| dim 取值范围 | 已覆盖 | 正向 dim、负向 dim、越界 dim |
| 参数张量形态 | 已覆盖 | 连续 Parameter、转置后的非连续 Parameter |
| shape | 已覆盖 | 0D / 1D / 2D / 3D 形状 |
| device | 已覆盖 | NPU Parameter，确认接口在 NPU 张量上调用 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体 stride 数值正确性 | 已覆盖 | 针对固定 shape 断言连续与转置场景下的具体 stride |
| 多 NPU 卡切换 | 当前用例聚焦单卡 NPU 功能验证，不依赖多卡环境 |
"""

import math

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Parameter.stride 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Parameter.stride 测试。")


def _make_npu_parameter(shape, transpose=False):
    _require_npu()
    numel = math.prod(shape) if len(shape) > 0 else 1
    base = torch.arange(1, 1 + numel, dtype=torch.float32, device=torch.device("npu:0")).reshape(shape)
    if transpose:
        if len(shape) < 2:
            raise ValueError("transpose=True 仅支持至少二维 shape。")
        base = base.transpose(0, 1)
    return torch.nn.Parameter(base)


@pytest.mark.parametrize(
    "shape, expected_stride",
    [
        ((), ()),
        ((5,), (1,)),
        ((2, 3), (3, 1)),
        ((2, 3, 4), (12, 4, 1)),
    ],
)
def test_parameter_stride_noarg_returns_tuple(shape, expected_stride):
    """验证无参调用返回 tuple，并对固定 shape 断言具体 stride。"""
    param = _make_npu_parameter(shape)

    stride_tuple = param.stride()

    assert isinstance(param, torch.nn.Parameter)
    assert param.device.type == "npu"
    assert isinstance(stride_tuple, tuple)
    assert stride_tuple == expected_stride
    assert len(stride_tuple) == param.dim()
    for idx in range(param.dim()):
        assert param.stride(idx) == expected_stride[idx]


@pytest.mark.parametrize(
    "shape, expected_stride",
    [
        ((), ()),
        ((5,), (1,)),
        ((2, 3), (3, 1)),
        ((2, 3, 4), (12, 4, 1)),
    ],
)
def test_parameter_stride_explicit_none_returns_tuple(shape, expected_stride):
    """验证显式传入 dim=None 时，行为与无参调用一致，并匹配具体 stride。"""
    param = _make_npu_parameter(shape)

    no_arg_stride = param.stride()
    none_stride = param.stride(None)

    assert isinstance(none_stride, tuple)
    assert no_arg_stride == expected_stride
    assert none_stride == no_arg_stride
    assert len(none_stride) == param.dim()


@pytest.mark.parametrize("shape, expected_stride", [((2, 3, 4), (12, 4, 1))])
@pytest.mark.parametrize("dim, expected_value", [(0, 12), (1, 4), (-1, 1)])
def test_parameter_stride_with_dim_returns_int(shape, expected_stride, dim, expected_value):
    """验证传入 dim 时返回 int，并支持负向索引及具体 stride 数值。"""
    param = _make_npu_parameter(shape)

    stride_tuple = param.stride()
    stride_value = param.stride(dim)

    assert isinstance(stride_value, int)
    assert stride_tuple == expected_stride
    assert stride_value == expected_value


def test_parameter_stride_transposed_noncontiguous_behavior():
    """验证连续与转置非连续 Parameter 的 stride 接口行为及具体数值。"""
    contiguous = _make_npu_parameter((2, 3))
    transposed = _make_npu_parameter((2, 3), transpose=True)

    contiguous_stride = contiguous.stride()
    transposed_stride = transposed.stride()

    assert contiguous.device.type == "npu"
    assert transposed.device.type == "npu"
    assert contiguous.is_contiguous()
    assert not transposed.is_contiguous()
    assert isinstance(contiguous_stride, tuple)
    assert isinstance(transposed_stride, tuple)
    assert contiguous_stride == (3, 1)
    assert transposed_stride == (1, 3)
    assert len(contiguous_stride) == len(transposed_stride) == 2
    assert contiguous_stride != transposed_stride
    assert transposed.stride(0) == 1
    assert transposed.stride(-1) == 3


@pytest.mark.parametrize(
    "bad_dim, expected_exc",
    [
        (0.5, TypeError),
        ("0", RuntimeError),
    ],
)
def test_parameter_stride_invalid_type_raises(bad_dim, expected_exc):
    """验证非整数 dim 会抛出类型异常。"""
    param = _make_npu_parameter((2, 3))

    with pytest.raises(expected_exc):
        param.stride(bad_dim)


@pytest.mark.parametrize("bad_dim", [2, -3])
def test_parameter_stride_out_of_range_raises(bad_dim):
    """验证 dim 越界时抛出 IndexError。"""
    param = _make_npu_parameter((2, 3))

    with pytest.raises(IndexError):
        param.stride(bad_dim)
