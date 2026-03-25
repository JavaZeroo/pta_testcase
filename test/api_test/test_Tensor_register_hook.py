"""
测试目的：
1. 验证 Tensor.register_hook 在 NPU 上的基本注册、触发、反注册与异常行为。
2. 覆盖 hook 参数的传入/不传、None/非 None、主要 callable 类型、返回值类型、leaf / non-leaf Tensor 以及边界值场景。
3. 仅验证接口语义、设备归属与异常，不做具体梯度数值正确性校验。

API 名称：Tensor.register_hook

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| hook 是否传入 | 已覆盖 | 传入 callable / 传入 None / 不传参 |
| hook 类型 | 已覆盖 | lambda / 普通函数 / 带 __call__ 的类实例 / 非 callable |
| hook 返回值 | 已覆盖 | 返回 Tensor / 返回 None / 返回非法类型 |
| Tensor 类型 | 已覆盖 | leaf Tensor / non-leaf Tensor |
| Tensor 边界值 | 已覆盖 | 标量 Tensor（0 维） |
| requires_grad | 已覆盖 | True / False |
| 反注册 | 已覆盖 | handle.remove() 后 hook 不再触发 |
| 正常/异常场景 | 已覆盖 | 正常触发、参数错误、返回值错误、requires_grad 错误 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体梯度数值精确校验 | 本文件仅验证 hook 触发、返回类型与设备行为，不做数值精度断言 |
| 多卡 / 分布式 NPU 场景 | 当前仅覆盖单卡基本功能路径，不依赖多卡环境 |
| 更复杂的 hook 执行顺序推导 | 该 API 重点是注册与触发，顺序相关细节不作为本文件目标 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Tensor.register_hook 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Tensor.register_hook 测试。")


def _npu_device():
    _require_npu()
    return torch.device("npu:0")


@pytest.fixture()
def npu_leaf_tensor():
    return torch.tensor([1.0, 2.0, 3.0], device=_npu_device(), requires_grad=True)


@pytest.fixture()
def npu_scalar_tensor():
    return torch.tensor(2.0, device=_npu_device(), requires_grad=True)


@pytest.fixture()
def npu_nonleaf_tensor():
    base = torch.tensor([1.0, 2.0, 3.0], device=_npu_device(), requires_grad=True)
    nonleaf = base * 2.0
    return base, nonleaf


def test_tensor_register_hook_missing_argument_raises_type_error(npu_leaf_tensor):
    """验证 register_hook 不传 hook 参数时抛出 TypeError。"""
    with pytest.raises(TypeError):
        npu_leaf_tensor.register_hook()


def test_tensor_register_hook_none_argument_raises_type_error(npu_leaf_tensor):
    """验证 register_hook 传入 None 时在 backward 阶段抛出 TypeError。"""
    handle = npu_leaf_tensor.register_hook(None)
    assert handle is not None

    with pytest.raises(TypeError):
        (npu_leaf_tensor * 2.0).sum().backward()


def test_tensor_register_hook_lambda_return_tensor_and_remove(npu_scalar_tensor):
    """验证 lambda hook、返回 Tensor、标量边界值以及 handle.remove() 生效。"""
    received_grads = []

    hook = lambda grad: received_grads.append(grad) or (grad + 1)  # noqa: E731

    handle = npu_scalar_tensor.register_hook(hook)
    assert handle is not None
    assert hasattr(handle, "remove")

    (npu_scalar_tensor * 3.0).backward()

    assert len(received_grads) == 1
    assert isinstance(received_grads[0], torch.Tensor)
    assert received_grads[0].device.type == "npu"
    assert npu_scalar_tensor.grad is not None
    assert isinstance(npu_scalar_tensor.grad, torch.Tensor)
    assert npu_scalar_tensor.grad.device.type == "npu"
    assert torch.equal(
        npu_scalar_tensor.grad,
        npu_scalar_tensor.new_tensor(4.0),
    )

    handle.remove()
    npu_scalar_tensor.grad = None
    prev_count = len(received_grads)
    (npu_scalar_tensor * 4.0).backward()
    assert len(received_grads) == prev_count
    assert npu_scalar_tensor.grad is not None
    assert npu_scalar_tensor.grad.device.type == "npu"


def test_tensor_register_hook_function_return_none_on_nonleaf(npu_nonleaf_tensor):
    """验证普通函数 hook、返回 None 以及 non-leaf Tensor 上的注册与触发。"""
    base, nonleaf = npu_nonleaf_tensor
    received_grads = []

    def hook_fn(grad):
        received_grads.append(grad)
        return None

    handle = nonleaf.register_hook(hook_fn)
    assert handle is not None

    nonleaf.retain_grad()
    nonleaf.sum().backward()

    assert len(received_grads) == 1
    assert isinstance(received_grads[0], torch.Tensor)
    assert received_grads[0].device.type == "npu"
    assert nonleaf.grad is not None
    assert isinstance(nonleaf.grad, torch.Tensor)
    assert nonleaf.grad.device.type == "npu"
    assert base.grad is not None
    assert base.grad.device.type == "npu"


def test_tensor_register_hook_multiple_hooks_with_callable_class_and_modify_grad(npu_leaf_tensor):
    """验证多个 hook、class __call__ 形式 hook 以及修改 grad 的场景。"""

    class GradRecorder:
        def __init__(self):
            self.calls = []

        def __call__(self, grad):
            self.calls.append(grad)
            return grad + 1

    class_hook = GradRecorder()
    second_calls = []

    def second_hook(grad):
        second_calls.append(grad)
        return None

    handle1 = npu_leaf_tensor.register_hook(class_hook)
    handle2 = npu_leaf_tensor.register_hook(second_hook)
    assert handle1 is not None
    assert handle2 is not None

    (npu_leaf_tensor * 5.0).sum().backward()

    assert len(class_hook.calls) == 1
    assert len(second_calls) == 1
    assert isinstance(class_hook.calls[0], torch.Tensor)
    assert isinstance(second_calls[0], torch.Tensor)
    assert class_hook.calls[0].device.type == "npu"
    assert second_calls[0].device.type == "npu"
    assert npu_leaf_tensor.grad is not None
    assert npu_leaf_tensor.grad.device.type == "npu"
    assert torch.equal(
        npu_leaf_tensor.grad,
        torch.full_like(npu_leaf_tensor, 6.0),
    )


def test_tensor_register_hook_non_callable_raises_type_error(npu_leaf_tensor):
    """验证非 callable hook 在 backward 阶段触发 TypeError。"""
    bad_hook = 123
    with pytest.raises(TypeError):
        handle = npu_leaf_tensor.register_hook(bad_hook)
        assert handle is not None
        (npu_leaf_tensor * 2.0).sum().backward()


def test_tensor_register_hook_invalid_return_type_raises_type_error(npu_leaf_tensor):
    """验证 hook 返回非法类型时，backward 抛出 TypeError。"""

    def bad_return_hook(grad):
        return "invalid-return-type"

    npu_leaf_tensor.register_hook(bad_return_hook)
    with pytest.raises(TypeError):
        (npu_leaf_tensor * 2.0).sum().backward()


def test_tensor_register_hook_tensor_without_requires_grad_raises():
    """验证 tensor 不需要梯度时注册 hook 会抛出 RuntimeError。"""
    no_grad_tensor = torch.tensor([1.0, 2.0], device=_npu_device())

    with pytest.raises(RuntimeError):
        no_grad_tensor.register_hook(lambda grad: grad)
