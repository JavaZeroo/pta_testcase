# 测试目的：验证 Tensor.to() API 在加速卡（NPU/GPU）上的功能行为，覆盖 dtype 转换、设备转换、
#           non_blocking、copy、memory_format 等全部主要入参路径。
# API 名称：Tensor.to
# 签名：Tensor.to(*args, **kwargs) → Tensor
#
# 覆盖维度表：
# | 覆盖维度           | 说明                                              | 覆盖情况                                |
# |--------------------|---------------------------------------------------|-----------------------------------------|
# | 空/非空            | dtype、device 均支持 None 与非 None              | 形式2中 dtype=None 只转设备；device=None 只转 dtype |
# | 枚举选项           | memory_format 枚举值                             | preserve_format / contiguous_format / channels_last 均覆盖 |
# | 参数类型           | dtype 传 torch.dtype；device 传字符串/device对象；other 传 Tensor | 均覆盖 |
# | 传参与不传参       | non_blocking / copy / memory_format 的默认值路径  | 均覆盖                                  |
# | 等价类/边界值      | 同 dtype 同 device（copy=False 返回 self）；copy=True 强制复制；标量/多维 tensor | 均覆盖 |
# | 正常传参场景       | cpu→加速卡、加速卡→cpu、加速卡→加速卡、dtype 转换、other tensor、memory_format | 均覆盖 |
# | 异常传参场景       | 无——文档未明确说明 Tensor.to 的稳定异常路径；不写脆弱负例 | N/A |
#
# 未覆盖项及原因：
# - float8/bfloat8 等实验性 dtype：后端支持情况未知，让测试自然失败。
# - sparse tensor .to()：后端不一定支持稀疏张量，不单独覆盖。
# - meta device：加速卡上无实际意义，不覆盖。
# - channels_last_3d：需要5D tensor，后端支持情况不确定，不单独覆盖。

import pytest
import torch


# ---------------------------------------------------------------------------
# 形式1：to(dtype, ...)  — 仅 dtype 转换，设备不变
# ---------------------------------------------------------------------------

class TestTensorToDtype:
    """调用形式1：tensor.to(dtype)"""

    def test_float32_to_float64(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(torch.float64)
        assert out.dtype == torch.float64
        assert out.device.type == device.type

    def test_float32_to_float16(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(torch.float16)
        assert out.dtype == torch.float16
        assert out.device.type == device.type

    def test_float32_to_bfloat16(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(torch.bfloat16)
        assert out.dtype == torch.bfloat16
        assert out.device.type == device.type

    def test_float32_to_int32(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(torch.int32)
        assert out.dtype == torch.int32
        assert out.device.type == device.type

    def test_float32_to_bool(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(torch.bool)
        assert out.dtype == torch.bool
        assert out.device.type == device.type

    def test_same_dtype_returns_self_when_no_copy(self, device):
        """copy=False（默认）且 dtype/device 相同 → 应返回同一对象"""
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(torch.float32)
        assert out.data_ptr() == t.data_ptr()

    def test_dtype_with_non_blocking_false(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(torch.float64, non_blocking=False)
        assert out.dtype == torch.float64

    def test_dtype_with_non_blocking_true(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(torch.float64, non_blocking=True)
        assert out.dtype == torch.float64
        assert out.device.type == device.type

    def test_dtype_with_copy_true(self, device):
        """copy=True 即使同 dtype 也强制返回新副本"""
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(torch.float32, copy=True)
        assert out.dtype == torch.float32
        # 强制 copy 时应与原张量不共享存储
        assert out.data_ptr() != t.data_ptr()

    def test_scalar_tensor_dtype_conversion(self, device):
        t = torch.tensor(1.0, device=device, dtype=torch.float32)
        out = t.to(torch.float64)
        assert out.dtype == torch.float64
        assert out.ndim == 0


# ---------------------------------------------------------------------------
# 形式2：to(device=..., dtype=..., ...)  — 设备转换（可附带 dtype）
# ---------------------------------------------------------------------------

class TestTensorToDevice:
    """调用形式2：tensor.to(device=...) / tensor.to(device=..., dtype=...)"""

    def test_cpu_to_accelerator_string_device(self, device_name, device):
        t = torch.randn(3, 4, device="cpu", dtype=torch.float32)
        out = t.to(device_name)
        assert out.device.type == device.type
        assert out.dtype == torch.float32

    def test_cpu_to_accelerator_device_object(self, device):
        t = torch.randn(3, 4, device="cpu", dtype=torch.float32)
        out = t.to(device)
        assert out.device.type == device.type

    def test_accelerator_to_cpu(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to("cpu")
        assert out.device.type == "cpu"
        assert out.dtype == torch.float32

    def test_accelerator_to_same_device(self, device):
        """已在目标 device 且 copy=False → 返回 self"""
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(device=device)
        assert out.device.type == device.type
        assert out.data_ptr() == t.data_ptr()

    def test_accelerator_to_cpu_with_dtype(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(device="cpu", dtype=torch.float64)
        assert out.device.type == "cpu"
        assert out.dtype == torch.float64

    def test_cpu_to_accelerator_with_dtype(self, device_name, device):
        t = torch.randn(3, 4, device="cpu", dtype=torch.float32)
        out = t.to(device=device_name, dtype=torch.float16)
        assert out.device.type == device.type
        assert out.dtype == torch.float16

    def test_device_only_dtype_unchanged(self, device_name, device):
        """只指定 device，dtype 不变"""
        t = torch.randn(3, 4, device="cpu", dtype=torch.float64)
        out = t.to(device=device_name)
        assert out.dtype == torch.float64
        assert out.device.type == device.type

    def test_device_none_means_dtype_only(self, device):
        """device=None 时只做 dtype 转换"""
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(device=None, dtype=torch.float16)
        assert out.dtype == torch.float16
        assert out.device.type == device.type

    def test_non_blocking_true_device_transfer(self, device_name, device):
        t = torch.randn(3, 4, device="cpu")
        out = t.to(device_name, non_blocking=True)
        assert out.device.type == device.type

    def test_non_blocking_false_device_transfer(self, device_name, device):
        t = torch.randn(3, 4, device="cpu")
        out = t.to(device_name, non_blocking=False)
        assert out.device.type == device.type

    def test_copy_true_same_device_and_dtype(self, device):
        """copy=True 即使已在正确 device/dtype 也强制复制"""
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(device=device, dtype=torch.float32, copy=True)
        assert out.device.type == device.type
        assert out.dtype == torch.float32
        assert out.data_ptr() != t.data_ptr()

    def test_copy_false_no_extra_copy_when_same(self, device):
        """copy=False（默认）同 device/dtype → 返回同一存储"""
        t = torch.randn(3, 4, device=device, dtype=torch.float32)
        out = t.to(device=device, dtype=torch.float32, copy=False)
        assert out.data_ptr() == t.data_ptr()


# ---------------------------------------------------------------------------
# 形式3：to(other, ...)  — 匹配另一个 tensor 的 dtype 和 device
# ---------------------------------------------------------------------------

class TestTensorToOther:
    """调用形式3：tensor.to(other)"""

    def test_to_other_matches_dtype_and_device(self, device):
        src = torch.randn(3, 4, device="cpu", dtype=torch.float32)
        other = torch.randn(2, 2, device=device, dtype=torch.float64)
        out = src.to(other)
        assert out.device.type == device.type
        assert out.dtype == torch.float64

    def test_to_other_same_backend_dtype_change(self, device):
        src = torch.randn(3, 4, device=device, dtype=torch.float32)
        other = torch.randn(1, device=device, dtype=torch.float16)
        out = src.to(other)
        assert out.device.type == device.type
        assert out.dtype == torch.float16

    def test_to_other_non_blocking(self, device):
        src = torch.randn(3, 4, device="cpu", dtype=torch.float32)
        other = torch.randn(1, device=device, dtype=torch.float64)
        out = src.to(other, non_blocking=True)
        assert out.device.type == device.type
        assert out.dtype == torch.float64

    def test_to_other_copy_true(self, device):
        src = torch.randn(3, 4, device=device, dtype=torch.float32)
        other = torch.randn(1, device=device, dtype=torch.float32)
        out = src.to(other, copy=True)
        assert out.dtype == torch.float32
        assert out.device.type == device.type
        # 强制 copy，应得到新副本
        assert out.data_ptr() != src.data_ptr()

    def test_to_other_same_dtype_and_device_no_copy(self, device):
        src = torch.randn(3, 4, device=device, dtype=torch.float32)
        other = torch.randn(1, device=device, dtype=torch.float32)
        out = src.to(other)
        # same dtype+device, copy=False → 返回 self
        assert out.data_ptr() == src.data_ptr()


# ---------------------------------------------------------------------------
# memory_format 参数
# ---------------------------------------------------------------------------

class TestTensorToMemoryFormat:
    """memory_format 参数的覆盖：preserve_format / contiguous_format / channels_last"""

    def test_memory_format_preserve(self, device):
        t = torch.randn(2, 3, 4, 4, device=device)
        out = t.to(memory_format=torch.preserve_format)
        assert out.device.type == device.type
        assert isinstance(out, torch.Tensor)

    def test_memory_format_contiguous(self, device):
        t = torch.randn(2, 3, 4, 4, device=device)
        out = t.to(memory_format=torch.contiguous_format)
        assert out.is_contiguous(memory_format=torch.contiguous_format)
        assert out.device.type == device.type

    def test_memory_format_channels_last(self, device):
        t = torch.randn(2, 3, 4, 4, device=device)
        out = t.to(memory_format=torch.channels_last)
        assert out.is_contiguous(memory_format=torch.channels_last)
        assert out.device.type == device.type

    def test_memory_format_channels_last_with_dtype(self, device):
        t = torch.randn(2, 3, 4, 4, device=device, dtype=torch.float32)
        out = t.to(dtype=torch.float16, memory_format=torch.channels_last)
        assert out.dtype == torch.float16
        assert out.is_contiguous(memory_format=torch.channels_last)
        assert out.device.type == device.type

    def test_memory_format_contiguous_from_channels_last(self, device):
        t = torch.randn(2, 3, 4, 4, device=device).to(memory_format=torch.channels_last)
        assert t.is_contiguous(memory_format=torch.channels_last)
        out = t.to(memory_format=torch.contiguous_format)
        assert out.is_contiguous(memory_format=torch.contiguous_format)
        assert out.device.type == device.type

    def test_memory_format_preserve_keeps_channels_last(self, device):
        t = torch.randn(2, 3, 4, 4, device=device).to(memory_format=torch.channels_last)
        out = t.to(memory_format=torch.preserve_format)
        assert out.is_contiguous(memory_format=torch.channels_last)
        assert out.device.type == device.type


# ---------------------------------------------------------------------------
# 返回对象通用检查
# ---------------------------------------------------------------------------

class TestTensorToReturnBehavior:
    """验证 .to() 返回对象为 Tensor、形状不变、requires_grad 传播等基本行为"""

    def test_return_is_tensor(self, device):
        t = torch.randn(3, 4, device=device)
        out = t.to(torch.float64)
        assert isinstance(out, torch.Tensor)

    def test_shape_preserved_dtype_conversion(self, device):
        t = torch.randn(2, 3, 5, device=device, dtype=torch.float32)
        out = t.to(torch.float16)
        assert out.shape == t.shape

    def test_shape_preserved_device_transfer(self, device):
        t = torch.randn(2, 3, 5, device="cpu")
        out = t.to(device)
        assert out.shape == t.shape

    def test_requires_grad_preserved(self, device):
        t = torch.randn(3, 4, device=device, dtype=torch.float32, requires_grad=True)
        out = t.to(torch.float64)
        assert out.requires_grad

    def test_1d_tensor_to_dtype(self, device):
        t = torch.tensor([1.0, 2.0, 3.0], device=device, dtype=torch.float32)
        out = t.to(torch.float64)
        assert out.dtype == torch.float64
        assert out.shape == (3,)

    def test_high_dim_tensor_device_transfer(self, device):
        t = torch.randn(2, 3, 4, 5, device="cpu")
        out = t.to(device)
        assert out.device.type == device.type
        assert out.shape == (2, 3, 4, 5)

    def test_same_device_and_dtype_is_self(self, device):
        """无 dtype/device 变化 + copy=False → 返回同一张量"""
        t = torch.randn(4, 4, device=device, dtype=torch.float32)
        out = t.to(device=device, dtype=torch.float32)
        assert out is t or out.data_ptr() == t.data_ptr()
