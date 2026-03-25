"""
测试目的：
1. 验证 torch._prims_common.make_contiguous_strides_for 在 NPU 环境下可正常调用，并返回合法的 tuple 结果。
2. 覆盖 shape 传参、缺参、常见类型（tuple/list/torch.Size）、空形状、含 0/1 的边界形状，以及 row_major 默认/显式传参场景。
3. 对部分已知 shape 补充精确 stride 断言，并在 NPU 上使用返回的 strides 构造张量，验证结果可被 NPU 接受。
4. 覆盖非法 shape、缺少位置参数等异常场景，并使用 pytest.raises 进行校验。

API 名称：torch._prims_common.make_contiguous_strides_for

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| shape | 已覆盖 | tuple / list / torch.Size；包含正常形状、空形状、含 0/1 的边界形状 |
| shape 是否传入 | 已覆盖 | 传入正常值、缺少位置参数 |
| row_major | 已覆盖 | 默认不传、显式 True、显式 False |
| 参数类型 | 已覆盖 | shape 覆盖 tuple/list/torch.Size；row_major 覆盖 bool |
| 返回类型 | 已覆盖 | 校验返回值为 tuple，且元素均为 int |
| NPU 环境 | 已覆盖 | 显式 import torch_npu，并使用 NPU 张量验证返回值可落地 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 更高维 shape 的完整 stride 公式枚举 | 当前仅对少量代表性 shape 做精确断言，其余场景仍以返回值形态和 NPU 可用性为主 |
| 多 NPU 卡切换 | 当前仅验证单卡 NPU 基础行为，未依赖多卡环境 |
| 符号维度 / 动态 shape | 该 API 本文件聚焦静态常见 shape，未构造 SymInt 相关场景 |
"""

import pytest

import torch
import torch_npu  # noqa: F401

from torch._prims_common import make_contiguous_strides_for


MISSING = object()


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 make_contiguous_strides_for 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 make_contiguous_strides_for 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device("npu:0")


def _assert_tuple_of_ints(strides):
    assert isinstance(strides, tuple)
    assert all(isinstance(item, int) for item in strides)


def _call_make_contiguous_strides_for(shape, row_major=MISSING):
    if row_major is MISSING:
        return make_contiguous_strides_for(shape)
    return make_contiguous_strides_for(shape, row_major=row_major)


def _assert_npu_roundtrip(npu_device, shape, strides):
    shape_tuple = tuple(shape)
    tensor = torch.empty_strided(shape_tuple, strides, device=npu_device)
    assert tuple(tensor.size()) == shape_tuple
    assert tensor.stride() == strides


@pytest.mark.parametrize(
    "shape,row_major",
    [
        pytest.param((2, 3), MISSING, id="tuple-default-row-major"),
        pytest.param([1], False, id="list-row-major-false-1d"),
        pytest.param(torch.Size([2, 3, 4]), False, id="torchsize-row-major-false-3d"),
        pytest.param((), True, id="empty-shape-explicit-true"),
        pytest.param((0, 3), False, id="zero-dim-row-major-false"),
        pytest.param((1, 1, 4), True, id="ones-shape-explicit-true"),
    ],
)
def test_make_contiguous_strides_for_valid_inputs_on_npu(npu_device, shape, row_major):
    """验证合法输入下可正常返回 tuple，且结果能在 NPU 上用于构造张量。"""
    result = _call_make_contiguous_strides_for(shape, row_major=row_major)

    _assert_tuple_of_ints(result)
    assert len(result) == len(tuple(shape))
    _assert_npu_roundtrip(npu_device, shape, result)


def test_make_contiguous_strides_for_row_major_true_exact_2d_stride_on_npu(npu_device):
    """验证 row_major=True 时 2D shape 返回精确的连续内存 stride。"""
    shape = (3, 4)
    result = make_contiguous_strides_for(shape, row_major=True)

    assert result == (4, 1)
    _assert_npu_roundtrip(npu_device, shape, result)


def test_make_contiguous_strides_for_row_major_false_exact_2d_stride_on_npu(npu_device):
    """验证 row_major=False 时 2D shape 返回与 row_major=True 不同的精确 stride。"""
    shape = (3, 4)
    row_major_true = make_contiguous_strides_for(shape, row_major=True)
    row_major_false = make_contiguous_strides_for(shape, row_major=False)

    assert row_major_true == (4, 1)
    assert row_major_false == (1, 3)
    assert row_major_false != row_major_true
    _assert_npu_roundtrip(npu_device, shape, row_major_false)


def test_make_contiguous_strides_for_explicit_row_major_false_on_npu(npu_device):
    """验证显式传入 row_major=False 时，1 维形状也能在 NPU 上正常构造。"""
    shape = (4,)
    result = make_contiguous_strides_for(shape, row_major=False)

    _assert_tuple_of_ints(result)
    assert len(result) == len(shape)
    _assert_npu_roundtrip(npu_device, shape, result)


def test_make_contiguous_strides_for_missing_shape_raises(npu_device):
    """验证缺少位置参数时抛出 TypeError。"""
    with pytest.raises(TypeError):
        make_contiguous_strides_for()


@pytest.mark.parametrize(
    "bad_shape, expected_exc",
    [
        (None, AssertionError),
        (3, AssertionError),
        ((-1,), RuntimeError),
        ((1, "x"), TypeError),
        ("abc", TypeError),
    ],
)
def test_make_contiguous_strides_for_invalid_shape_raises(npu_device, bad_shape, expected_exc):
    """验证非法 shape 输入时通过 pytest.raises 捕获异常。"""
    with pytest.raises(expected_exc):
        make_contiguous_strides_for(bad_shape)
