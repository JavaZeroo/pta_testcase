"""
测试目的：
1. 验证 Tensor.untyped_storage() 在 NPU 上可正常调用，且返回值类型为 torch.UntypedStorage。
2. 验证返回 storage 的 device 与张量 device 一致，且 storage 的字节大小与张量元素数量/元素字节数关系符合预期。
3. 验证不同 dtype、不同 shape、连续/非连续张量、空张量与标量张量等场景下的基础行为。
4. 验证视图之间共享底层 storage 的行为。
5. 验证该无参接口在“传参/不传参”维度上的签名约束：正常不传参可调用，传入多余参数会抛出异常。

API 名称：Tensor.untyped_storage

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 参数传参/不传参 | 已覆盖 | 不传参正常调用；传入位置参数/关键字参数时触发 TypeError |
| None/非None | 不适用 | 该 API 为无参接口，无 None 入参可测 |
| dtype | 已覆盖 | float32 / float16 / int32 / int64 / bool |
| shape | 已覆盖 | 1D / 2D / 3D / 标量 / 空张量 |
| contiguous | 已覆盖 | 连续张量 / 非连续视图张量 |
| storage_size_vs_tensor_size | 已覆盖 | contiguous 场景下校验 nbytes = numel * element_size；view 场景下校验共享 storage 且 storage 大小不小于视图张量所需字节数 |
| shared_storage_between_views | 已覆盖 | 基础张量与其视图调用 untyped_storage() 后共享同一底层 storage |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| None 入参分支 | Tensor.untyped_storage() 为无参接口，不存在 None/非 None 入参 |
| storage 内容数值正确性 | 本 API 关注底层 storage 暴露与共享关系，不做元素值层面的数值正确性校验 |
| 多卡/跨设备 storage 行为 | 当前用例仅验证单卡 NPU 基本功能，不依赖多 NPU 环境 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Tensor.untyped_storage 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Tensor.untyped_storage 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device("npu:0")


def _make_tensor(device, dtype, shape, fill_with_arange=True):
    if shape == ():
        if dtype == torch.bool:
            return torch.tensor(True, dtype=dtype, device=device)
        if dtype.is_floating_point:
            return torch.tensor(3.5, dtype=dtype, device=device)
        return torch.tensor(7, dtype=dtype, device=device)

    numel = 1
    for dim in shape:
        numel *= dim

    if dtype == torch.bool:
        base = torch.ones(shape, dtype=dtype, device=device)
        return base

    if fill_with_arange:
        base = torch.arange(numel, device=device).reshape(shape)
    else:
        base = torch.ones(shape, device=device)
    return base.to(dtype)


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16, torch.int32, torch.int64, torch.bool])
@pytest.mark.parametrize("shape", [(8,), (2, 3), (2, 2, 2)])
def test_untyped_storage_normal_contiguous_cases(npu_device, dtype, shape):
    """验证连续张量在不同 dtype / shape 下的返回类型、设备与存储大小关系。"""
    tensor = _make_tensor(npu_device, dtype, shape)

    storage = tensor.untyped_storage()

    assert type(storage) is torch.UntypedStorage
    assert storage.device == tensor.device
    assert tensor.is_contiguous()
    assert storage.nbytes() == tensor.numel() * tensor.element_size()


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16, torch.int32, torch.int64, torch.bool])
def test_untyped_storage_scalar_boundary_case(npu_device, dtype):
    """验证标量张量调用 untyped_storage() 的边界行为。"""
    tensor = _make_tensor(npu_device, dtype, ())

    storage = tensor.untyped_storage()

    assert type(storage) is torch.UntypedStorage
    assert storage.device == tensor.device
    assert tensor.shape == torch.Size([])
    assert storage.nbytes() == tensor.numel() * tensor.element_size()


def test_untyped_storage_rejects_extra_arguments(npu_device):
    """验证无参接口对多余位置参数和关键字参数的签名约束。"""
    tensor = torch.ones((2, 3), dtype=torch.float32, device=npu_device)

    with pytest.raises(TypeError):
        tensor.untyped_storage(None)

    with pytest.raises(TypeError):
        tensor.untyped_storage(dummy=1)


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16, torch.int32, torch.int64, torch.bool])
def test_untyped_storage_empty_tensor_boundary_case(npu_device, dtype):
    """验证空张量调用 untyped_storage() 的边界行为。"""
    tensor = torch.empty((0,), dtype=dtype, device=npu_device)

    storage = tensor.untyped_storage()

    assert type(storage) is torch.UntypedStorage
    assert storage.device == tensor.device
    assert tensor.numel() == 0
    assert storage.nbytes() == tensor.numel() * tensor.element_size()


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16, torch.int32, torch.int64, torch.bool])
def test_untyped_storage_non_contiguous_view_shares_storage(npu_device, dtype):
    """验证非连续视图与基张量共享同一底层 storage。"""
    base = _make_tensor(npu_device, dtype, (4, 4, 2))
    view = base[:, ::2, :]

    base_storage = base.untyped_storage()
    view_storage = view.untyped_storage()

    assert type(view_storage) is torch.UntypedStorage
    assert view.device == base.device
    assert not view.is_contiguous()
    assert base_storage.device == base.device
    assert view_storage.device == view.device
    assert base_storage.data_ptr() == view_storage.data_ptr()
    assert base_storage.nbytes() == base.numel() * base.element_size()
    assert view_storage.nbytes() == base_storage.nbytes()
    assert view_storage.nbytes() >= view.numel() * view.element_size()


def test_untyped_storage_returns_same_storage_object_for_multiple_views(npu_device):
    """验证多个视图调用 untyped_storage() 时共享同一底层 storage。"""
    base = torch.arange(24, device=npu_device, dtype=torch.float32).reshape(2, 3, 4)
    view1 = base.transpose(0, 1)
    view2 = base[..., 1:]

    storage1 = view1.untyped_storage()
    storage2 = view2.untyped_storage()

    assert type(storage1) is torch.UntypedStorage
    assert type(storage2) is torch.UntypedStorage
    assert storage1.device == base.device
    assert storage2.device == base.device
    assert storage1.data_ptr() == storage2.data_ptr() == base.untyped_storage().data_ptr()
    assert storage1.nbytes() == storage2.nbytes() == base.untyped_storage().nbytes()
