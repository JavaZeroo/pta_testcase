"""
测试目的：
1. 验证 Tensor.requires_grad 相关属性在 NPU 上的默认值、读取、写入与原地切换行为。
2. 覆盖 leaf / non-leaf、float / int / None、标量 / 空张量等关键维度，包含正常与异常场景。
3. 说明该 API 本身无显式入参，但通过 requires_grad_ / 属性赋值覆盖“传 / 不传”“None / 非 None”等行为分支。

API 名称：Tensor.requires_grad

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| API 直接读取（无参数） | 已覆盖 | 直接访问 requires_grad 属性，验证返回值类型与默认值 |
| 原地接口参数传 / 不传 | 已覆盖 | requires_grad_() 省略参数使用默认 True；requires_grad_(False) 显式传参 |
| None / 非 None | 已覆盖 | None 作为非法值触发异常；True / False 为合法值 |
| 主要枚举值 | 已覆盖 | 布尔枚举 True / False |
| 主要类型 | 已覆盖 | float Tensor 正常；int Tensor 不允许开启梯度 |
| 正常场景 | 已覆盖 | 默认值读取、显式开启、关闭、detach 后重新开启 |
| 异常场景 | 已覆盖 | int dtype、non-leaf、None 参数均触发异常 |
| 边界值 | 已覆盖 | 标量 Tensor、空 Tensor |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 反向传播数值正确性 | 本测试聚焦 requires_grad 属性语义与异常行为，不验证梯度数值 |
| 多 NPU 卡 / 跨卡场景 | 当前用例仅验证单卡 NPU 上的接口行为，未依赖多卡环境 |
| 非布尔数值自动转换 | 该 API 语义要求 bool，使用非法类型即可覆盖异常路径，不再重复测试数值隐式转换 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Tensor.requires_grad 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Tensor.requires_grad 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device(f"npu:{torch.npu.current_device()}")


def test_tensor_requires_grad_default_false_scalar_tensor(npu_device):
    """验证标量 Tensor 的默认 requires_grad 为 False，且张量位于 NPU。"""
    tensor = torch.tensor(3.0, device=npu_device)

    assert tensor.device.type == "npu"
    assert isinstance(tensor.requires_grad, bool)
    assert tensor.requires_grad is False
    assert tensor.is_leaf is True


def test_tensor_requires_grad_empty_tensor_creation_true(npu_device):
    """验证空 Tensor 在创建时显式设置 requires_grad=True 的行为。"""
    tensor = torch.empty((0, 2), device=npu_device, requires_grad=True)

    assert tensor.device.type == "npu"
    assert isinstance(tensor.requires_grad, bool)
    assert tensor.requires_grad is True
    assert tensor.is_leaf is True
    assert tensor.shape == torch.Size([0, 2])


def test_tensor_requires_grad_inplace_setter_on_leaf_can_toggle(npu_device):
    """验证 leaf Tensor 可通过 requires_grad_ 省略参数和显式参数在 True/False 之间切换。"""
    tensor = torch.ones((2, 2), device=npu_device)

    assert tensor.device.type == "npu"
    assert isinstance(tensor.requires_grad, bool)
    assert tensor.requires_grad is False
    assert tensor.is_leaf is True

    tensor.requires_grad_()
    assert isinstance(tensor.requires_grad, bool)
    assert tensor.requires_grad is True

    tensor.requires_grad_(False)
    assert isinstance(tensor.requires_grad, bool)
    assert tensor.requires_grad is False


def test_tensor_requires_grad_property_set_true_on_npu_float_tensor(npu_device):
    """验证 NPU 上的 float Tensor 可直接通过属性赋值开启 requires_grad。"""
    tensor = torch.tensor([1.0, 2.0], device=npu_device)

    assert tensor.device.type == "npu"
    assert tensor.requires_grad is False

    tensor.requires_grad = True

    assert isinstance(tensor.requires_grad, bool)
    assert tensor.requires_grad is True


def test_tensor_requires_grad_property_set_none_raises(npu_device):
    """验证 NPU 上的 float Tensor 通过属性赋值 None 时会触发异常。"""
    tensor = torch.tensor([1.0, 2.0], device=npu_device)

    assert tensor.device.type == "npu"
    assert tensor.requires_grad is False

    with pytest.raises((TypeError, RuntimeError)):
        tensor.requires_grad = None


def test_tensor_requires_grad_int_dtype_with_true_raises(npu_device):
    """验证 NPU 上的整型 Tensor 不允许通过 requires_grad_ 开启梯度。"""
    tensor = torch.tensor([1, 2], dtype=torch.int32, device=npu_device)

    assert tensor.device.type == "npu"

    with pytest.raises(RuntimeError):
        tensor.requires_grad_(True)


def test_tensor_requires_grad_on_non_leaf_raises(npu_device):
    """验证 non-leaf Tensor 不允许通过 requires_grad_ 修改 requires_grad。"""
    leaf = torch.tensor([1.0, 2.0], device=npu_device, requires_grad=True)
    non_leaf = leaf + 1.0

    assert non_leaf.device.type == "npu"
    assert non_leaf.is_leaf is False
    assert isinstance(non_leaf.requires_grad, bool)
    assert non_leaf.requires_grad is True

    with pytest.raises(RuntimeError):
        non_leaf.requires_grad_(False)


def test_tensor_requires_grad_detach_resets_and_allows_reenable(npu_device):
    """验证 detach 后 requires_grad 会重置为 False，且可在 NPU 上重新开启。"""
    leaf = torch.tensor([1.0, 2.0], device=npu_device, requires_grad=True)
    non_leaf = leaf * 3.0
    detached = non_leaf.detach()

    assert detached.device.type == "npu"
    assert detached.is_leaf is True
    assert isinstance(detached.requires_grad, bool)
    assert detached.requires_grad is False

    detached.requires_grad_(True)
    assert isinstance(detached.requires_grad, bool)
    assert detached.requires_grad is True
