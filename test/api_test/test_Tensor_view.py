# 测试目的：验证 Tensor.view API 在加速卡（NPU/GPU）上的功能行为与接口覆盖
# API 名称：Tensor.view
# 签名：Tensor.view(*shape) → Tensor  /  Tensor.view(dtype) → Tensor
#
# 覆盖维度：
# | 覆盖维度          | 说明                                              | 覆盖情况                              |
# |-------------------|---------------------------------------------------|---------------------------------------|
# | 空/非空           | shape 各种组合、dtype 有无                        | 覆盖 shape 和 dtype 两种调用形式      |
# | 枚举选项          | dtype：float32→int32, float32→uint8, float32→cfloat | 覆盖主要 dtype 转换目标             |
# | 参数类型          | int 可变参、torch.Size 对象、包含 -1 的推断参数   | 全覆盖                                |
# | 传参与不传参      | shape 多 int vs torch.Size vs view_as             | 覆盖                                  |
# | 等价类/边界值     | 空 tensor、stride-0 tensor、非连续 tensor         | 覆盖                                  |
# | 正常传参场景      | 合法 shape 变换，API 可正常调用，返回类型合理      | 覆盖                                  |
# | 异常传参场景      | 元素数量不匹配、多个 -1、不兼容非连续 tensor      | 覆盖（文档及上游测试明确会抛 RuntimeError）|
#
# 未覆盖项及原因：
# - TorchScript dtype 视图（文档标注 Warning: not supported by TorchScript，与加速卡测试无关）
# - 分布式 dtensor 场景（需要分布式环境，不适合单机测试）
# - stride 不整除 upsize 错误（属于 dtype view 的边缘 error 路径，已选取典型场景，穷举略去）

import pytest
import torch


# ---------------------------------------------------------------------------
# 基础 shape 变换
# ---------------------------------------------------------------------------

class TestTensorViewShapeBasic:
    """验证 view 基础 shape 变换路径（多 int 参数）。"""

    def test_view_2d_to_1d(self, device):
        """4x4 → 16，多 int 参数形式。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(16)
        assert y.shape == torch.Size([16])
        assert y.device.type == device.type
        assert isinstance(y, torch.Tensor)

    def test_view_1d_to_2d(self, device):
        """15 → 3x5，多 int 参数形式。"""
        x = torch.randn(15, device=device)
        y = x.view(3, 5)
        assert y.shape == torch.Size([3, 5])
        assert y.device.type == device.type

    def test_view_2d_reshape(self, device):
        """4x4 → 2x8，元素数量不变。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(2, 8)
        assert y.shape == torch.Size([2, 8])

    def test_view_4d_to_2d(self, device):
        """1x2x3x4 → 6x4，高维压缩。"""
        x = torch.randn(1, 2, 3, 4, device=device)
        y = x.view(6, 4)
        assert y.shape == torch.Size([6, 4])

    def test_view_1d_to_4d(self, device):
        """24 → 1x2x3x4，低维扩展。"""
        x = torch.randn(24, device=device)
        y = x.view(1, 2, 3, 4)
        assert y.shape == torch.Size([1, 2, 3, 4])


# ---------------------------------------------------------------------------
# torch.Size 传参
# ---------------------------------------------------------------------------

class TestTensorViewTorchSize:
    """验证传入 torch.Size 对象的路径。"""

    def test_view_with_torch_size(self, device):
        """用 torch.Size 指定目标 shape。"""
        x = torch.randn(15, device=device)
        y = x.view(torch.Size([3, 5]))
        assert y.shape == torch.Size([3, 5])
        assert y.device.type == device.type

    def test_view_with_torch_size_multi_dim(self, device):
        """torch.Size 多维。"""
        x = torch.randn(24, device=device)
        y = x.view(torch.Size([2, 3, 4]))
        assert y.shape == torch.Size([2, 3, 4])


# ---------------------------------------------------------------------------
# -1 推断维度
# ---------------------------------------------------------------------------

class TestTensorViewInferDim:
    """验证含 -1 的推断维度路径。"""

    def test_view_infer_first_dim(self, device):
        """(-1, 5) 推断第一维。"""
        x = torch.randn(15, device=device)
        y = x.view(-1, 5)
        assert y.shape == torch.Size([3, 5])

    def test_view_infer_last_dim(self, device):
        """(3, -1) 推断最后一维。"""
        x = torch.randn(15, device=device)
        y = x.view(3, -1)
        assert y.shape == torch.Size([3, 5])

    def test_view_infer_single_dim_flatten(self, device):
        """(-1,) 全展平。"""
        x = torch.randn(3, 4, device=device)
        y = x.view(-1)
        assert y.shape == torch.Size([12])

    def test_view_infer_middle_dim(self, device):
        """(2, -1, 4) 推断中间维。"""
        x = torch.randn(2, 3, 4, device=device)
        y = x.view(2, -1, 4)
        assert y.shape == torch.Size([2, 3, 4])

    def test_view_infer_with_multi_dim(self, device):
        """多维中有一个 -1。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(2, -1, 2)
        assert y.shape == torch.Size([2, 4, 2])


# ---------------------------------------------------------------------------
# 空 tensor
# ---------------------------------------------------------------------------

class TestTensorViewEmpty:
    """验证空 tensor 的 view 路径。"""

    def test_view_empty_tensor_to_1d(self, device):
        """空 tensor view(0)。"""
        x = torch.empty(0, device=device)
        y = x.view(0)
        assert y.shape == torch.Size([0])
        assert y.device.type == device.type

    def test_view_empty_tensor_multi_dim(self, device):
        """空 tensor view 到多维。"""
        x = torch.empty(0, device=device)
        y = x.view(0, 3, 0, 1)
        assert y.shape == torch.Size([0, 3, 0, 1])

    def test_view_empty_multi_dim_back_to_1d(self, device):
        """多维空 tensor view 回 0。"""
        x = torch.empty(0, device=device)
        y = x.view(0, 3, 0, 1).view(0)
        assert y.shape == torch.Size([0])

    def test_view_empty_infer_zero(self, device):
        """空 tensor (-1) 推断为 0。"""
        x = torch.empty(0, device=device)
        y = x.view(-1)
        assert y.shape == torch.Size([0])

    def test_view_empty_infer_with_nonzero_dims(self, device):
        """空 tensor (10, 3, -1) 推断最后维为 0。"""
        x = torch.empty(0, device=device)
        y = x.view(10, 3, -1)
        assert y.shape == torch.Size([10, 3, 0])


# ---------------------------------------------------------------------------
# stride-0 tensor（expand 后）
# ---------------------------------------------------------------------------

class TestTensorViewStridedZero:
    """验证 stride 0 维度的 tensor 视图路径。"""

    def test_view_stride0_flatten(self, device):
        """expand 后的 tensor view(-1)。"""
        x = torch.empty(1, 1, device=device).expand(3, 4)
        contig = x.clone()
        y = x.view(-1)
        expected = contig.view(-1)
        assert y.shape == expected.shape

    def test_view_stride0_add_dims(self, device):
        """expand 后的 tensor 加冗余维度 view。"""
        x = torch.empty(1, 1, device=device).expand(3, 4)
        contig = x.clone()
        y = x.view(1, -1, 1)
        expected = contig.view(1, -1, 1)
        assert y.shape == expected.shape

    def test_view_stride0_reshape_dims(self, device):
        """expand 后的 tensor 重排 view。"""
        x = torch.empty(1, 1, device=device).expand(3, 4)
        contig = x.clone()
        y = x.view(6, 2, 1)
        expected = contig.view(6, 2, 1)
        assert y.shape == expected.shape


# ---------------------------------------------------------------------------
# 数据共享（view 是原 tensor 的视图）
# ---------------------------------------------------------------------------

class TestTensorViewDataSharing:
    """验证 view 共享数据路径（修改 view 后原 tensor 也变化）。"""

    def test_view_shares_data(self, device):
        """修改 view 后原 tensor 对应位置变化。"""
        t = torch.ones(5, 5, device=device)
        v = t.view(25)
        v[6] = 0.0
        assert t[1, 1].item() == 0.0

    def test_view_data_ptr_same(self, device):
        """view 与原 tensor 共享 data_ptr。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(16)
        assert x.data_ptr() == y.data_ptr()

    def test_view_chain_shares_data(self, device):
        """链式 view 共享数据。"""
        x = torch.ones(2, 3, 4, device=device)
        y = x.view(6, 4)
        z = y.view(24)
        z[0] = 99.0
        assert x[0, 0, 0].item() == 99.0


# ---------------------------------------------------------------------------
# view_as（以另一个 tensor 为 shape 模板）
# ---------------------------------------------------------------------------

class TestTensorViewAs:
    """验证 view_as 路径（template tensor）。"""

    def test_view_as_basic(self, device):
        """用 template tensor 的 shape 做 view。"""
        t = torch.randn(15, device=device)
        template = torch.rand(3, 5, device=device)
        v = t.view_as(template)
        assert v.shape == template.shape
        assert v.device.type == device.type

    def test_view_as_shares_data(self, device):
        """view_as 返回的是视图，与原 tensor 共享数据。"""
        t = torch.ones(5, 5, device=device)
        e = torch.empty(25, device=device)
        v = t.view_as(e)
        v[6] = 0.0
        assert t[1, 1].item() == 0.0

    def test_view_as_4d(self, device):
        """4D 模板 view_as。"""
        t = torch.randn(24, device=device)
        template = torch.empty(2, 3, 4, 1, device=device)
        v = t.view_as(template)
        assert v.shape == torch.Size([2, 3, 4, 1])


# ---------------------------------------------------------------------------
# dtype 视图（重新解读底层数据）
# ---------------------------------------------------------------------------

class TestTensorViewDtype:
    """验证 view(dtype) 路径——float32 重新解读为其他类型。"""

    def test_view_float32_to_int32(self, device):
        """float32 → int32（元素大小相同，4字节）。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(torch.int32)
        assert y.dtype == torch.int32
        assert y.shape == x.shape
        assert y.device.type == device.type

    def test_view_float32_to_uint8(self, device):
        """float32 → uint8（4字节→1字节，最后维扩大4倍）。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(torch.uint8)
        assert y.dtype == torch.uint8
        # 最后一维变为 4*4=16
        assert y.shape == torch.Size([4, 16])
        assert y.device.type == device.type

    def test_view_float32_to_cfloat(self, device):
        """float32 → cfloat（4字节→8字节，最后维缩小一半）。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(torch.cfloat)
        assert y.dtype == torch.cfloat
        # 最后一维变为 4//2=2
        assert y.shape == torch.Size([4, 2])
        assert y.device.type == device.type

    def test_view_dtype_data_ptr_same(self, device):
        """dtype view 共享底层存储（data_ptr 相同）。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(torch.int32)
        assert x.data_ptr() == y.data_ptr()

    def test_view_float32_to_int8(self, device):
        """float32 → int8（4字节→1字节）。"""
        x = torch.randn(4, 8, device=device)
        y = x.view(torch.int8)
        assert y.dtype == torch.int8
        assert y.shape == torch.Size([4, 32])

    def test_view_int8_to_int16(self, device):
        """int8 → int16（1字节→2字节）。"""
        x = torch.zeros(4, 16, dtype=torch.int8, device=device)
        y = x.view(torch.int16)
        assert y.dtype == torch.int16
        assert y.shape == torch.Size([4, 8])


# ---------------------------------------------------------------------------
# 非连续 tensor 的合法 view（连续块内操作）
# ---------------------------------------------------------------------------

class TestTensorViewNonContiguousValid:
    """验证非连续 tensor 中合法 view 的路径（仅在连续子块内重排）。"""

    def test_view_non_contiguous_valid_within_contiguous_chunk(self, device):
        """非连续 tensor 内合法 view，仅在连续维度块内重排。"""
        tensor = (
            torch.rand(4, 2, 5, 1, 6, 2, 9, 3, device=device)
            .transpose(-1, 2)
            .transpose(-2, 3)
        )
        contig_tensor = tensor.clone()
        # 跨越连续块内部的合法重排
        view_size = [8, 1, 3, 3, 3, 4, 1, 3, 5]
        y = tensor.view(*view_size)
        expected = contig_tensor.view(*view_size)
        assert y.shape == torch.Size(view_size)
        assert y.device.type == device.type

    def test_view_non_contiguous_add_size1_dims(self, device):
        """非连续 tensor 插入 size-1 维度（合法）。"""
        tensor = (
            torch.rand(4, 2, 5, 1, 6, 2, 9, 3, device=device)
            .transpose(-1, 2)
            .transpose(-2, 3)
        )
        contig_tensor = tensor.clone()
        view_size = [1, 1, 2, 1, 4, 3, 1, 1, 9, 1, 2, 1, 2, 3, 1, 5, 1, 1]
        y = tensor.view(*view_size)
        expected = contig_tensor.view(*view_size)
        assert y.shape == torch.Size(view_size)


# ---------------------------------------------------------------------------
# 异常场景（文档和上游测试明确会抛 RuntimeError）
# ---------------------------------------------------------------------------

class TestTensorViewRaises:
    """验证非法参数下 view 会抛出 RuntimeError 的路径。"""

    def test_view_incompatible_numel(self, device):
        """元素数量不匹配，应抛 RuntimeError。"""
        x = torch.randn(15, device=device)
        with pytest.raises(RuntimeError):
            x.view(15, 0)

    def test_view_incompatible_shape(self, device):
        """shape 乘积与元素数量不匹配，应抛 RuntimeError。"""
        x = torch.randn(15, device=device)
        with pytest.raises(RuntimeError):
            x.view(7, -1)

    def test_view_multiple_neg1(self, device):
        """多个 -1，应抛 RuntimeError。"""
        x = torch.randn(15, device=device)
        with pytest.raises(RuntimeError):
            x.view(15, -1, -1)

    def test_view_empty_ambiguous_neg1(self, device):
        """空 tensor (-1, 0) 无法推断，应抛 RuntimeError。"""
        x = torch.empty(0, device=device)
        with pytest.raises(RuntimeError):
            x.view(-1, 0)

    def test_view_non_contiguous_invalid_crossing(self, device):
        """非连续 tensor 跨越连续块边界的非法 view，应抛 RuntimeError。"""
        tensor = (
            torch.rand(4, 2, 5, 1, 6, 2, 9, 3, device=device)
            .transpose(-1, 2)
            .transpose(-2, 3)
        )
        # 跨越 [4,2] 和 [3] 两个连续块，非法
        with pytest.raises(RuntimeError):
            tensor.view(24, 9, 6, 2, 1, 5)

    def test_view_non_contiguous_invalid_full_flatten(self, device):
        """非连续 tensor 全展平，应抛 RuntimeError。"""
        tensor = (
            torch.rand(4, 2, 5, 1, 6, 2, 9, 3, device=device)
            .transpose(-1, 2)
            .transpose(-2, 3)
        )
        with pytest.raises(RuntimeError):
            tensor.view(-1)


# ---------------------------------------------------------------------------
# 返回类型与设备断言
# ---------------------------------------------------------------------------

class TestTensorViewReturnType:
    """验证 view 返回对象的类型和设备属性。"""

    def test_view_returns_tensor(self, device):
        """view 返回 torch.Tensor 类型。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(16)
        assert isinstance(y, torch.Tensor)

    def test_view_device_preserved(self, device):
        """view 后设备类型保持不变。"""
        x = torch.randn(3, 4, device=device)
        y = x.view(12)
        assert y.device.type == device.type

    def test_view_dtype_preserved(self, device):
        """shape view 不改变 dtype。"""
        x = torch.randn(4, 4, dtype=torch.float32, device=device)
        y = x.view(16)
        assert y.dtype == torch.float32

    def test_view_is_not_clone(self, device):
        """view 返回的是视图，不是副本（修改后原 tensor 也变）。"""
        x = torch.ones(4, 4, device=device)
        y = x.view(16)
        y[0] = 999.0
        assert x[0, 0].item() == 999.0

    def test_view_grad_info(self, device):
        """view 不带 requires_grad 时，返回 tensor 也不带 grad。"""
        x = torch.randn(4, 4, device=device)
        y = x.view(16)
        assert not y.requires_grad

    def test_view_with_requires_grad(self, device):
        """requires_grad=True 时，view 返回的 tensor 仍携带 grad。"""
        x = torch.randn(4, 4, device=device, requires_grad=True)
        y = x.view(16)
        assert y.requires_grad
