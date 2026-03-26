# 测试目的：验证 torch._prims_common.make_contiguous_strides_for 在 NPU 环境下的功能行为与接口覆盖
# API 名称：torch._prims_common.make_contiguous_strides_for
#
# 覆盖参数维度：
#
# | 覆盖维度              | 说明                                                                  | 覆盖情况                                                                      |
# |-----------------------|-----------------------------------------------------------------------|-------------------------------------------------------------------------------|
# | 空/非空（None/非None）| shape 为空元组 ()                                                     | 覆盖：空 shape 返回空元组 ()                                                  |
# | 枚举选项              | row_major=True / row_major=False                                      | 覆盖：两个取值均有测试                                                        |
# | 参数类型              | shape 为 tuple[int, ...]，各维度正整数 / 含 0 / 含 1                  | 覆盖：正常维度、含零维度、含一维度                                            |
# | 传参与不传参          | row_major 默认不传（True）vs 显式传参                                 | 覆盖：默认调用与显式传 True/False                                             |
# | 等价类/边界值         | 0D(空)、1D、2D、3D shape；shape 含 0；shape 含 1                      | 覆盖：各维度等价类以及边界值（0、1）                                          |
# | 正常传参场景          | 合法输入下 API 可正常调用                                             | 覆盖：所有主要 shape 和 row_major 组合均正常调用并返回合理结果                |
# | 异常传参场景          | N/A（validate_shape 抛异常）                                          | 未覆盖（见下方未覆盖项说明）                                                  |
#
# 源码分支覆盖：
#   分支 1：not shape → 返回 ()                     → test_empty_shape
#   分支 2：row_major=True → 返回 result            → test_1d_row_major / test_2d_row_major / test_3d_row_major
#   分支 3：row_major=False + len(shape) < 2 → 返回 result（与 row_major=True 等价）
#                                                   → test_row_major_false_1d / test_row_major_false_0d_equiv
#   分支 4：row_major=False + len(shape) >= 2 → 返回 Fortran 连续步长
#                                                   → test_row_major_false_2d / test_row_major_false_3d
#   分支 5：shape 含 0 维度 → 触发 sym_max(l, 1)    → test_shape_with_zero_dim
#   分支 6：shape 含 1 维度 → 正常乘法路径           → test_shape_with_one_dim
#   分支 7：返回类型为 tuple                         → 各 test 均断言 isinstance(result, tuple)
#   分支 8：与 torch.empty 实际 tensor strides 对比  → test_compare_with_tensor_strides_*
#
# 未覆盖项：
# - validate_shape 内部对非法 shape 的异常（如负数维度）：validate_shape 的实现细节在上下文中未提供，
#   且 PyTorch 文档中未明确该 API 的异常行为，避免写脆弱的 pytest.raises 猜测。
# - is_nested_int 为 True 的路径：需要特殊的 NestedTensor 内部对象，无法在常规测试中直接构造。

import pytest
import torch
import torch_npu  # noqa: F401


def setup_module(module):
    """确保 NPU 可用，否则跳过整个模块。"""
    if not torch.npu.is_available():
        pytest.skip("NPU not available")


def get_api():
    """获取被测 API，若不存在则跳过。"""
    if not hasattr(torch._prims_common, "make_contiguous_strides_for"):
        pytest.skip("torch._prims_common.make_contiguous_strides_for not available")
    return torch._prims_common.make_contiguous_strides_for


# ---------------------------------------------------------------------------
# 基础可调用性与返回类型
# ---------------------------------------------------------------------------

class TestReturnType:
    """验证 API 可调用且始终返回 tuple。"""

    def test_returns_tuple_empty_shape(self):
        fn = get_api()
        result = fn(())
        assert isinstance(result, tuple)

    def test_returns_tuple_1d(self):
        fn = get_api()
        result = fn((5,))
        assert isinstance(result, tuple)

    def test_returns_tuple_2d(self):
        fn = get_api()
        result = fn((3, 4))
        assert isinstance(result, tuple)

    def test_returns_tuple_3d(self):
        fn = get_api()
        result = fn((2, 3, 4))
        assert isinstance(result, tuple)


# ---------------------------------------------------------------------------
# 分支 1：空 shape
# ---------------------------------------------------------------------------

class TestEmptyShape:
    """空 shape 返回空元组。"""

    def test_empty_shape_returns_empty_tuple(self):
        fn = get_api()
        result = fn(())
        assert result == ()

    def test_empty_shape_row_major_false(self):
        """row_major=False 且 shape 为空时，len(shape) < 2，走相同路径。"""
        fn = get_api()
        result = fn((), row_major=False)
        assert result == ()


# ---------------------------------------------------------------------------
# 分支 2：row_major=True（默认）
# ---------------------------------------------------------------------------

class TestRowMajorTrue:
    """row_major=True 时返回 C 连续（行主序）步长。"""

    def test_1d_default(self):
        """1D shape，默认 row_major=True。"""
        fn = get_api()
        result = fn((5,))
        assert len(result) == 1
        assert result == (1,)

    def test_1d_explicit_row_major(self):
        """1D shape，显式传 row_major=True。"""
        fn = get_api()
        result = fn((5,), row_major=True)
        assert result == (1,)

    def test_2d_row_major(self):
        """2D shape，行主序步长：stride[0]=4, stride[1]=1。"""
        fn = get_api()
        result = fn((3, 4))
        assert len(result) == 2
        assert result == (4, 1)

    def test_3d_row_major(self):
        """3D shape，行主序步长：(3*4, 4, 1) = (12, 4, 1)。"""
        fn = get_api()
        result = fn((2, 3, 4))
        assert len(result) == 3
        assert result == (12, 4, 1)

    def test_4d_row_major(self):
        """4D shape，步长维度数与 shape 一致。"""
        fn = get_api()
        result = fn((2, 3, 4, 5))
        assert len(result) == 4
        assert result == (60, 20, 5, 1)


# ---------------------------------------------------------------------------
# 分支 3 & 4：row_major=False
# ---------------------------------------------------------------------------

class TestRowMajorFalse:
    """row_major=False 的 Fortran 连续步长逻辑。"""

    def test_row_major_false_1d(self):
        """1D 时 len(shape) < 2，row_major=False 走 return result 分支，结果与 True 相同。"""
        fn = get_api()
        result_true = fn((5,), row_major=True)
        result_false = fn((5,), row_major=False)
        assert result_true == result_false

    def test_row_major_false_2d(self):
        """2D 时走 Fortran 路径：最后两维变成 (1, max(shape[-2], 1))。"""
        fn = get_api()
        result = fn((3, 4), row_major=False)
        # result[:-2] = ()，后两维 = (1, max(3, 1)) = (1, 3)
        assert len(result) == 2
        assert result[-1] == max(3, 1)
        assert result[-2] == 1

    def test_row_major_false_3d(self):
        """3D 时前缀步长保留，最后两维变成 Fortran 格式。"""
        fn = get_api()
        result = fn((2, 3, 4), row_major=False)
        assert len(result) == 3
        # result[:-2] 保留前缀，最后两维 = (1, max(shape[-2], 1)) = (1, max(3, 1)) = (1, 3)
        assert result[-2] == 1
        assert result[-1] == max(3, 1)

    def test_row_major_false_4d(self):
        """4D 时验证前两维步长保留，最后两维为 Fortran 格式。"""
        fn = get_api()
        result = fn((2, 3, 4, 5), row_major=False)
        assert len(result) == 4
        assert result[-2] == 1
        assert result[-1] == max(4, 1)

    def test_row_major_false_empty_shape(self):
        """空 shape 时 row_major=False 返回空元组。"""
        fn = get_api()
        result = fn((), row_major=False)
        assert result == ()


# ---------------------------------------------------------------------------
# 分支 5：shape 含 0 维度（触发 sym_max(l, 1)）
# ---------------------------------------------------------------------------

class TestShapeWithZeroDim:
    """含零维度时 sym_max(l, 1) 使步长计算基于 1 而非 0。"""

    def test_1d_zero_dim(self):
        """单维为 0 时步长应为 1（从 sym_max(0, 1)=1 开始反向乘）。"""
        fn = get_api()
        result = fn((0,))
        assert isinstance(result, tuple)
        assert len(result) == 1
        assert result == (1,)

    def test_2d_with_zero_first_dim(self):
        """第一维为 0，第二维为 4。"""
        fn = get_api()
        result = fn((0, 4))
        assert isinstance(result, tuple)
        assert len(result) == 2
        # stride[1]=1, stride[0]=sym_max(4,1)=4
        assert result == (4, 1)

    def test_2d_with_zero_second_dim(self):
        """第一维为 3，第二维为 0。"""
        fn = get_api()
        result = fn((3, 0))
        assert isinstance(result, tuple)
        assert len(result) == 2
        # stride[1]=1, stride[0]=sym_max(0,1)=1
        assert result == (1, 1)

    def test_2d_both_zero(self):
        """两维均为 0。"""
        fn = get_api()
        result = fn((0, 0))
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result == (1, 1)

    def test_row_major_false_with_zero(self):
        """row_major=False + 含零维度。"""
        fn = get_api()
        result = fn((0, 4), row_major=False)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[-2] == 1
        assert result[-1] == max(0, 1)


# ---------------------------------------------------------------------------
# 分支 6：shape 含 1 维度（正常乘法路径）
# ---------------------------------------------------------------------------

class TestShapeWithOneDim:
    """含 1 维度时走正常乘法路径（sym_max(1, 1)=1，不改变步长）。"""

    def test_1d_single_element(self):
        fn = get_api()
        result = fn((1,))
        assert result == (1,)

    def test_2d_with_one(self):
        fn = get_api()
        result = fn((1, 4))
        assert result == (4, 1)

    def test_2d_all_ones(self):
        fn = get_api()
        result = fn((1, 1))
        assert result == (1, 1)

    def test_3d_with_one_in_middle(self):
        fn = get_api()
        result = fn((2, 1, 4))
        assert result == (4, 4, 1)


# ---------------------------------------------------------------------------
# 与实际 torch.empty tensor 的 strides 对比（行主序）
# ---------------------------------------------------------------------------

class TestCompareWithTensorStrides:
    """在 NPU 上创建 tensor，验证 API 计算结果与 tensor.stride() 一致。"""

    def _npu_strides(self, shape):
        """在 NPU 上创建连续 tensor 并返回其 strides。"""
        t = torch.empty(shape, device="npu")
        return t.stride()

    def test_1d_matches_tensor(self):
        fn = get_api()
        shape = (7,)
        assert fn(shape) == self._npu_strides(shape)

    def test_2d_matches_tensor(self):
        fn = get_api()
        shape = (3, 4)
        assert fn(shape) == self._npu_strides(shape)

    def test_3d_matches_tensor(self):
        fn = get_api()
        shape = (2, 3, 4)
        assert fn(shape) == self._npu_strides(shape)

    def test_4d_matches_tensor(self):
        fn = get_api()
        shape = (2, 3, 4, 5)
        assert fn(shape) == self._npu_strides(shape)

    def test_large_shape_matches_tensor(self):
        fn = get_api()
        shape = (8, 16, 32, 64)
        assert fn(shape) == self._npu_strides(shape)

    def test_shape_with_one_matches_tensor(self):
        fn = get_api()
        shape = (1, 4, 1, 8)
        assert fn(shape) == self._npu_strides(shape)


# ---------------------------------------------------------------------------
# 步长长度与 shape 长度一致性
# ---------------------------------------------------------------------------

class TestStridesLengthConsistency:
    """返回步长的长度必须与 shape 长度相同。"""

    def test_length_1d(self):
        fn = get_api()
        shape = (10,)
        assert len(fn(shape)) == len(shape)

    def test_length_2d(self):
        fn = get_api()
        shape = (3, 4)
        assert len(fn(shape)) == len(shape)

    def test_length_3d(self):
        fn = get_api()
        shape = (2, 3, 4)
        assert len(fn(shape)) == len(shape)

    def test_length_row_major_false_2d(self):
        fn = get_api()
        shape = (3, 4)
        assert len(fn(shape, row_major=False)) == len(shape)

    def test_length_row_major_false_3d(self):
        fn = get_api()
        shape = (2, 3, 4)
        assert len(fn(shape, row_major=False)) == len(shape)
