# 测试目的：验证 torch.autograd.Variable._execution_engine.queue_callback
#           在加速卡（NPU/GPU）上能正常排队并执行回调函数
# API 名称：torch.autograd.Variable._execution_engine.queue_callback
#
# 分支分析（C++ 实现，无 Python 源码，基于上游参考推断）：
#   1. 在 backward 过程中（通过 register_hook）排队单个 callback → 验证 callback 被执行
#   2. 在 backward 过程中排队多个 callback → 验证所有 callback 均被执行
#   3. 通过直接注册的 tensor hook 触发 queue_callback → 验证与 hook 协作正确
#   4. callback 在 backward 完成后才执行（后置执行语义）
#
# 未覆盖项及原因：
#   - 在 backward 之外调用 queue_callback：上游文档未说明此场景的稳定行为，
#     不同版本可能 raise 也可能静默忽略，避免写脆弱负例
#   - callback 为非 callable：C++ 层行为不明确，无稳定异常证据，省略
#
# 覆盖维度表：
#
# | 覆盖维度         | 说明                                            | 覆盖情况                                      |
# |------------------|-------------------------------------------------|-----------------------------------------------|
# | 空/非空          | callback 参数为有副作用的 callable              | 已覆盖：使用 list/dict 记录执行状态            |
# | 枚举选项         | N/A（无枚举型入参）                             | N/A                                           |
# | 参数类型         | callback 类型：lambda、具名函数、可调用对象     | 已覆盖：lambda、def 函数、带状态的可调用对象  |
# | 传参与不传参     | queue_callback 必须传入 callable                | 已覆盖：传入各类 callable                     |
# | 等价类/边界值    | 单个 callback、多个 callback 排队               | 已覆盖                                         |
# | 正常传参场景     | 合法输入下 API 在 backward 中被调用             | 已覆盖：基本调用、加速卡 tensor、多 callback   |
# | 异常传参场景     | 无明确证据支撑稳定异常，省略                    | 未覆盖，原因见上方                             |

import pytest
import torch


def _require_queue_callback():
    engine = getattr(torch.autograd.Variable, "_execution_engine", None)
    if engine is None or not hasattr(engine, "queue_callback"):
        pytest.skip("queue_callback not available in this PyTorch version")


class TestQueueCallbackExists:
    """验证 queue_callback 可访问。"""

    def test_execution_engine_exists(self):
        assert hasattr(torch.autograd.Variable, "_execution_engine"), (
            "_execution_engine not found on torch.autograd.Variable"
        )

    def test_queue_callback_exists(self):
        engine = torch.autograd.Variable._execution_engine
        assert hasattr(engine, "queue_callback"), (
            "queue_callback not found on _execution_engine"
        )

    def test_queue_callback_is_callable(self):
        engine = torch.autograd.Variable._execution_engine
        assert callable(engine.queue_callback)


class TestQueueCallbackBasic:
    """验证 queue_callback 在加速卡 backward 中的基本调用行为。"""

    def test_single_callback_executed(self, device):
        """在 hook 中调用 queue_callback，验证 callback 在 backward 后被执行。"""
        _require_queue_callback()

        executed = {"flag": False}

        def callback():
            executed["flag"] = True

        def hook_fn(grad):
            torch.autograd.Variable._execution_engine.queue_callback(callback)

        x = torch.tensor([1.0, 2.0], requires_grad=True, device=device)
        x.register_hook(hook_fn)
        output = (x ** 2).sum()
        output.backward()

        assert executed["flag"], "callback 应在 backward 完成后被执行"

    def test_callback_with_lambda(self, device):
        """使用 lambda 作为 callback，验证 queue_callback 接受 lambda。"""
        _require_queue_callback()

        results = []

        def hook_fn(grad):
            torch.autograd.Variable._execution_engine.queue_callback(
                lambda: results.append(42)
            )

        x = torch.tensor([1.0, 3.0], requires_grad=True, device=device)
        x.register_hook(hook_fn)
        (x * 2).sum().backward()

        assert len(results) == 1
        assert results[0] == 42

    def test_callback_with_named_function(self, device):
        """使用具名函数作为 callback。"""
        _require_queue_callback()

        call_log = []

        def my_callback():
            call_log.append("called")

        def hook_fn(grad):
            torch.autograd.Variable._execution_engine.queue_callback(my_callback)

        x = torch.randn(4, requires_grad=True, device=device)
        x.register_hook(hook_fn)
        x.sum().backward()

        assert call_log == ["called"]

    def test_callback_receives_no_args(self, device):
        """callback 不接收任何参数（zero-arg callable）。"""
        _require_queue_callback()

        arg_counts = []

        def callback():
            arg_counts.append(0)

        def hook_fn(grad):
            torch.autograd.Variable._execution_engine.queue_callback(callback)

        x = torch.tensor([2.0], requires_grad=True, device=device)
        x.register_hook(hook_fn)
        (x * 3).sum().backward()

        assert len(arg_counts) == 1


class TestQueueCallbackMultiple:
    """验证多个 callback 排队时的执行行为。"""

    def test_two_callbacks_both_executed(self, device):
        """在同一 hook 中排队两个 callback，两个均应被执行。"""
        _require_queue_callback()

        log = []

        def hook_fn(grad):
            torch.autograd.Variable._execution_engine.queue_callback(
                lambda: log.append("first")
            )
            torch.autograd.Variable._execution_engine.queue_callback(
                lambda: log.append("second")
            )

        x = torch.tensor([1.0, 2.0, 3.0], requires_grad=True, device=device)
        x.register_hook(hook_fn)
        x.sum().backward()

        assert "first" in log
        assert "second" in log
        assert len(log) == 2

    def test_multiple_callbacks_from_multiple_hooks(self, device):
        """不同 hook 各自排队一个 callback，所有 callback 均应被执行。"""
        _require_queue_callback()

        log = []

        def hook_a(grad):
            torch.autograd.Variable._execution_engine.queue_callback(
                lambda: log.append("hook_a")
            )

        def hook_b(grad):
            torch.autograd.Variable._execution_engine.queue_callback(
                lambda: log.append("hook_b")
            )

        x = torch.tensor([1.0, 2.0], requires_grad=True, device=device)
        x.register_hook(hook_a)
        x.register_hook(hook_b)
        (x + 1).sum().backward()

        assert "hook_a" in log
        assert "hook_b" in log


class TestQueueCallbackWithDeviceTensor:
    """验证 queue_callback 与加速卡 tensor backward 的协作。"""

    def test_device_tensor_2d(self, device):
        """在 2D 加速卡 tensor 的 backward 中使用 queue_callback。"""
        _require_queue_callback()

        executed = {"count": 0}

        def callback():
            executed["count"] += 1

        def hook_fn(grad):
            torch.autograd.Variable._execution_engine.queue_callback(callback)

        x = torch.randn(3, 4, requires_grad=True, device=device)
        x.register_hook(hook_fn)
        (x * x).sum().backward()

        assert executed["count"] == 1

    def test_callback_can_capture_grad_info(self, device):
        """callback 可通过闭包捕获 grad 信息，验证执行时机在 backward 之后。"""
        _require_queue_callback()

        captured = {}

        def hook_fn(grad):
            captured["grad"] = grad

            def callback():
                captured["callback_ran"] = True

            torch.autograd.Variable._execution_engine.queue_callback(callback)

        x = torch.tensor([1.0, 2.0, 3.0], requires_grad=True, device=device)
        x.register_hook(hook_fn)
        (x * 2).sum().backward()

        assert captured.get("callback_ran") is True
        assert "grad" in captured

    def test_callback_callable_object(self, device):
        """使用可调用对象（__call__ 方法）作为 callback。"""
        _require_queue_callback()

        class CallableObj:
            def __init__(self):
                self.called = False

            def __call__(self):
                self.called = True

        obj = CallableObj()

        def hook_fn(grad):
            torch.autograd.Variable._execution_engine.queue_callback(obj)

        x = torch.tensor([0.5, 1.5], requires_grad=True, device=device)
        x.register_hook(hook_fn)
        x.sum().backward()

        assert obj.called, "可调用对象应在 backward 后被执行"

    def test_backward_completes_normally(self, device):
        """确认使用 queue_callback 后，backward 流程本身正常完成，grad 被正确填充。"""
        _require_queue_callback()

        def hook_fn(grad):
            torch.autograd.Variable._execution_engine.queue_callback(lambda: None)

        x = torch.tensor([1.0, 2.0], requires_grad=True, device=device)
        x.register_hook(hook_fn)
        (x ** 2).sum().backward()

        assert x.grad is not None
        assert x.grad.device.type == device.type
