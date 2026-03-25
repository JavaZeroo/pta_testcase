"""
测试目的：
1. 验证 torch.nn.Parameter.grad 在 NPU 上的默认状态、反向传播生成状态、清空状态、预置状态与再次累积行为。
2. 验证 grad 赋值支持 None / Tensor 两类常见场景，并覆盖错误类型、错误形状、0 维边界 Tensor 等异常场景。
3. 验证 requires_grad=False 的 Parameter 在 NPU 上 backward 后仍不会产生自身 grad。

API 名称：torch.nn.Parameter.grad

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 是否显式设置 grad | 已覆盖 | 覆盖未设置、手动设置 Tensor、手动清空为 None |
| grad 初始状态 | 已覆盖 | Parameter 创建后 grad 默认 None |
| backward 后 grad 状态 | 已覆盖 | NPU 上 backward 后 grad 由 None 变为 Tensor |
| 预置非 None grad | 已覆盖 | 先手动写入 NPU Tensor，再执行 backward |
| grad 设备 | 已覆盖 | grad 始终保持在 NPU 上 |
| grad 形状 | 已覆盖 | grad.shape 与 Parameter.shape 保持一致 |
| grad 类型 | 已覆盖 | 覆盖 Tensor、None、非法标量/对象类型 |
| 异常场景 | 已覆盖 | 覆盖错误形状、0 维边界 Tensor、错误类型赋值 |
| requires_grad 开关 | 已覆盖 | 覆盖 requires_grad=True / False 两种状态 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 梯度数值正确性 | 本文件聚焦 grad 属性的状态、类型、设备与异常，不做具体数值校验 |
| 多卡/分布式场景 | 当前测试目标是单卡 NPU 上的基础属性行为，不依赖多卡环境 |
| autograd hook、优化器等上层联动 | 本文件仅验证 Parameter.grad 属性本身，不扩展到训练框架集成场景 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.nn.Parameter.grad 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.nn.Parameter.grad 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device(f"npu:{torch.npu.current_device()}")


def _make_parameter(npu_device, shape=(2, 3), requires_grad=True):
    data = torch.ones(shape, device=npu_device)
    return torch.nn.Parameter(data, requires_grad=requires_grad)


def test_parameter_grad_default_is_none(npu_device):
    """验证 Parameter 创建后 grad 默认是 None，且参数位于 NPU。"""
    param = _make_parameter(npu_device)

    assert param.device.type == "npu"
    assert param.grad is None


def test_parameter_grad_after_backward_on_npu(npu_device):
    """验证 NPU 上 backward 后 Parameter.grad 由 None 变为 Tensor，且设备/形状正确。"""
    param = _make_parameter(npu_device, shape=(2, 3))

    loss = (param * 2.0).sum()
    loss.backward()

    assert param.grad is not None
    assert isinstance(param.grad, torch.Tensor)
    assert param.grad.device.type == "npu"
    assert param.grad.shape == param.shape


def test_parameter_grad_accepts_none_and_tensor_assignment(npu_device):
    """验证 grad 可以清空为 None，并重新赋值为同设备 Tensor。"""
    param = _make_parameter(npu_device, shape=(2, 3))

    # 先制造一次非 None 状态，再清空为 None，覆盖“非 None -> None”链路。
    (param * 3.0).sum().backward()
    assert param.grad is not None
    assert isinstance(param.grad, torch.Tensor)
    assert param.grad.device.type == "npu"

    param.grad = None
    assert param.grad is None

    reassigned_grad = torch.full_like(param, 5.0)
    param.grad = reassigned_grad

    assert param.grad is not None
    assert isinstance(param.grad, torch.Tensor)
    assert param.grad.device.type == "npu"
    assert param.grad.shape == param.shape


def test_parameter_grad_accumulates_into_existing_tensor_on_npu(npu_device):
    """验证 grad 预置为 NPU Tensor 后，backward 仍会在同一 Tensor 上累积。"""
    param = _make_parameter(npu_device, shape=(2, 3))
    param.grad = torch.zeros_like(param)
    before_ptr = param.grad.data_ptr()
    expected_single_backward_grad = torch.full_like(param, 4.0)

    loss = (param * 4.0).sum()
    loss.backward(retain_graph=True)

    assert param.grad is not None
    assert isinstance(param.grad, torch.Tensor)
    assert param.grad.device.type == "npu"
    assert param.grad.shape == param.shape
    assert param.grad.data_ptr() == before_ptr
    assert torch.equal(param.grad, expected_single_backward_grad)

    after_first_ptr = param.grad.data_ptr()
    loss.backward()

    assert param.grad is not None
    assert isinstance(param.grad, torch.Tensor)
    assert param.grad.device.type == "npu"
    assert param.grad.shape == param.shape
    assert param.grad.data_ptr() == after_first_ptr
    assert torch.equal(param.grad, expected_single_backward_grad * 2)


def test_parameter_grad_device_mismatch_assignment_raises(npu_device):
    """验证给 NPU Parameter.grad 赋值 CPU Tensor 时会抛出设备不匹配异常。"""
    param = _make_parameter(npu_device, shape=(2, 3))

    with pytest.raises((RuntimeError, ValueError, TypeError)):
        param.grad = torch.ones((2, 3), device="cpu")


def test_parameter_grad_invalid_shape_assignment_raises(npu_device):
    """验证给 grad 赋值错误形状的 Tensor 时会抛出异常。"""
    param = _make_parameter(npu_device, shape=(2, 3))

    with pytest.raises((RuntimeError, ValueError, TypeError)):
        param.grad = torch.ones((3, 2), device=npu_device)


def test_parameter_grad_invalid_type_assignment_raises(npu_device):
    """验证给 grad 赋值非法类型对象时会抛出异常。"""
    param = _make_parameter(npu_device, shape=(2, 3))

    with pytest.raises((TypeError, RuntimeError, ValueError, AttributeError)):
        param.grad = 1


def test_parameter_grad_scalar_tensor_assignment_raises(npu_device):
    """验证给 grad 赋值 0 维边界 Tensor 时会抛出异常。"""
    param = _make_parameter(npu_device, shape=(2, 3))

    with pytest.raises((RuntimeError, ValueError, TypeError)):
        param.grad = torch.tensor(1.0, device=npu_device)


def test_parameter_grad_requires_grad_false_stays_none(npu_device):
    """验证 requires_grad=False 的 Parameter 在 backward 后仍不生成自身 grad。"""
    param = _make_parameter(npu_device, shape=(2, 3), requires_grad=False)
    other = torch.ones((2, 3), device=npu_device, requires_grad=True)

    assert param.requires_grad is False
    assert param.grad is None

    loss = (other * param).sum()
    loss.backward()

    assert param.grad is None
    assert other.grad is not None
    assert isinstance(other.grad, torch.Tensor)
    assert other.grad.device.type == "npu"
    assert other.grad.shape == other.shape
