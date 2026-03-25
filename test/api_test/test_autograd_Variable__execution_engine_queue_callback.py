"""
测试目的：
1. 验证 torch.autograd.Variable._execution_engine.queue_callback 在 NPU 上可正常接收 callback，并在 backward 完成后触发执行。
2. 验证支持多种 callable 形态（函数 / lambda / callable 对象），支持多次队列回调，并对非 callable、错误签名等异常场景抛出 TypeError。
3. 验证参数不传时会触发参数绑定错误，None/非 None 场景均有覆盖。
4. 验证回调配合 NPU Tensor 的反向传播链路可正常工作。

API 名称：torch.autograd.Variable._execution_engine.queue_callback

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 参数传/不传 | 已覆盖 | 传入合法 callback；不传时触发 TypeError |
| None/非None | 已覆盖 | None / 非 None 非法参数 |
| 主要枚举值 | 不适用 | 该 API 无枚举型参数 |
| callable 类型 | 已覆盖 | function / lambda |
| callable 对象类型 | 已覆盖 | 带 __call__ 的实例 |
| 回调执行时机 | 已覆盖 | 在 backward 完成后执行 |
| 多个回调队列 | 已覆盖 | 连续 queue 多个 callback |
| 边界值 | 已覆盖 | 单个回调 / 多个回调，覆盖最小与组合场景 |
| 非 callable 入参 | 已覆盖 | int / None，均应抛出 TypeError |
| callable 但签名错误 | 已覆盖 | 传入需要参数的 callable，在 backward 阶段触发 TypeError |
| NPU Tensor 参与 backward | 已覆盖 | 使用 NPU Tensor 构造反向传播链路 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 回调内部主动抛出异常的传播路径 | 当前聚焦基础可用性与参数校验，回调内部异常会增加用例不稳定性，未展开 |
| 多卡 / 跨设备场景 | 当前环境仅验证单卡 NPU 基本功能，不依赖多卡拓扑 |
| 回调执行顺序的强约束 | 当前用例验证“全部被执行”，不对内部调度顺序做实现细节约束 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu_queue_callback_engine():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 queue_callback 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 queue_callback 测试。")

    variable = getattr(torch.autograd, "Variable", None)
    engine = getattr(variable, "_execution_engine", None)
    if engine is None or not hasattr(engine, "queue_callback"):
        pytest.skip("当前 NPU 后端未暴露 Variable._execution_engine.queue_callback，无法执行该测试。")
    return engine


@pytest.fixture()
def npu_engine():
    return _require_npu_queue_callback_engine()


@pytest.fixture()
def npu_input_tensor():
    _require_npu_queue_callback_engine()
    return torch.tensor([1.0, 2.0, 3.0], device=torch.device("npu"), requires_grad=True)


def _run_backward_with_callback(npu_input_tensor, callback, npu_engine):
    assert callable(npu_engine.queue_callback)

    def hook(_grad):
        npu_engine.queue_callback(callback)

    npu_input_tensor.register_hook(hook)
    loss = (npu_input_tensor * 2).sum()
    assert npu_input_tensor.device.type == "npu"
    assert loss.device.type == "npu"
    assert loss.requires_grad is True
    loss.backward()
    if hasattr(torch, "npu"):
        torch.npu.synchronize()


def test_queue_callback_missing_argument_raises_type_error(npu_engine):
    """验证 callback 参数不传时会触发参数绑定错误。"""
    npu_input_tensor = torch.tensor([1.0, 2.0], device=torch.device("npu"), requires_grad=True)

    def hook(_grad):
        npu_engine.queue_callback()

    npu_input_tensor.register_hook(hook)
    loss = (npu_input_tensor * 2).sum()
    assert loss.device.type == "npu"

    with pytest.raises(TypeError):
        loss.backward()


@pytest.mark.parametrize("callback_kind", ["function", "lambda"])
def test_queue_callback_invoked_after_backward_on_npu(npu_input_tensor, npu_engine, callback_kind):
    """验证有效 callable 在 backward 完成后会被触发。"""
    calls = []

    if callback_kind == "function":

        def callback():
            calls.append("function")

    else:
        callback = lambda: calls.append("lambda")  # noqa: E731

    assert callable(callback)
    assert calls == []

    _run_backward_with_callback(npu_input_tensor, callback, npu_engine)

    assert len(calls) == 1
    assert calls[0] == callback_kind
    assert npu_input_tensor.grad is not None
    assert npu_input_tensor.grad.device.type == "npu"


def test_queue_callback_callable_object_invoked_on_npu(npu_engine):
    """验证 callable 对象实例可被 queue_callback 接收并在 backward 后执行。"""
    calls = []

    class CallbackObject:
        def __call__(self):
            calls.append("object")

    callback = CallbackObject()
    assert callable(callback)
    assert calls == []

    npu_input_tensor = torch.tensor([5.0, 6.0], device=torch.device("npu"), requires_grad=True)
    npu_input_tensor.register_hook(lambda _grad: npu_engine.queue_callback(callback))
    loss = (npu_input_tensor * 4).sum()
    assert loss.device.type == "npu"
    loss.backward()
    if hasattr(torch, "npu"):
        torch.npu.synchronize()

    assert calls == ["object"]
    assert npu_input_tensor.grad is not None
    assert npu_input_tensor.grad.device.type == "npu"


def test_queue_callback_multiple_callbacks_are_all_invoked_on_npu(npu_engine):
    """验证连续队列多个 callback 时，backward 后均会被执行。"""
    calls = []
    npu_input_tensor = torch.tensor([3.0, 4.0], device=torch.device("npu"), requires_grad=True)

    def callback_one():
        calls.append("one")

    callback_two = lambda: calls.append("two")  # noqa: E731

    assert callable(callback_one)
    assert callable(callback_two)
    assert calls == []

    def hook(_grad):
        npu_engine.queue_callback(callback_one)
        npu_engine.queue_callback(callback_two)

    npu_input_tensor.register_hook(hook)

    loss = (npu_input_tensor * 3).sum()
    assert loss.device.type == "npu"
    loss.backward()
    if hasattr(torch, "npu"):
        torch.npu.synchronize()

    assert len(calls) == 2
    assert "one" in calls
    assert "two" in calls
    assert npu_input_tensor.grad is not None
    assert npu_input_tensor.grad.device.type == "npu"


def test_queue_callback_callable_with_required_argument_raises_on_backward(npu_engine):
    """验证 callable 本身合法但签名不匹配时，会在 backward 阶段抛出异常。"""
    def callback_with_required_arg(grad):
        return grad

    npu_input_tensor = torch.tensor([7.0, 8.0], device=torch.device("npu"), requires_grad=True)
    npu_input_tensor.register_hook(lambda _grad: npu_engine.queue_callback(callback_with_required_arg))
    loss = (npu_input_tensor * 5).sum()
    assert loss.device.type == "npu"

    with pytest.raises(TypeError):
        loss.backward()


@pytest.mark.parametrize("bad_callback", [123, None])
def test_queue_callback_non_callable_raises_type_error(npu_engine, bad_callback):
    """验证非 callable 入参会抛出 TypeError。"""
    npu_input_tensor = torch.tensor([9.0, 10.0], device=torch.device("npu"), requires_grad=True)

    def hook(_grad):
        npu_engine.queue_callback(bad_callback)

    npu_input_tensor.register_hook(hook)
    loss = (npu_input_tensor * 6).sum()
    assert loss.device.type == "npu"

    with pytest.raises(TypeError):
        loss.backward()
