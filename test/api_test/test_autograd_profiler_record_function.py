# 测试目的：验证 torch.autograd.profiler.record_function 在加速卡（NPU/GPU）上的基本功能行为
# API 名称：torch.autograd.profiler.record_function
#
# 该 API 是一个 context manager / function decorator，用于在 autograd profiler 中
# 为代码块或函数添加标签，以便在性能分析时识别。
# 继承自 contextlib.ContextDecorator，支持 with 语句和 @decorator 两种用法。
#
# 签名：class torch.autograd.profiler.record_function(name, args=None)
# 参数：
#   name (str): 代码块标签
#   args (Optional[str]): 可选的参数字符串，默认 None
#
# 源码分支分析：
# 1. __init__: 初始化 name、args、run_callbacks_on_exit=True、record=None
# 2. __enter__: 调用 torch.ops.profiler._record_function_enter_new(name, args)
# 3. __exit__ 分支 B: run_callbacks_on_exit=True → 调用 _record_function_exit
# 4. 作为装饰器（contextlib.ContextDecorator 继承）
#
# 覆盖维度：
#
# | 覆盖维度                  | 说明                                              | 覆盖情况                                                     |
# |---------------------------|---------------------------------------------------|--------------------------------------------------------------|
# | 空/非空（None 或其他值）  | args=None 与 args 非 None 两条路径                | 已覆盖                                                       |
# | 枚举选项                  | N/A（无枚举型入参）                               | N/A                                                          |
# | 参数类型                  | name: str；args: Optional[str]                    | 已覆盖                                                       |
# | 传参与不传参              | args 可选，覆盖传入与使用默认值两种情形           | 已覆盖                                                       |
# | 等价类/边界值             | 空字符串名称、含特殊字符名称、嵌套 context       | 已覆盖                                                       |
# | 正常传参场景              | with 语句、装饰器、嵌套、加速卡 tensor 操作中使用 | 已覆盖                                                       |
# | 异常传参场景              | 不覆盖（_call_end_callbacks_on_future 需要 JIT Future，成本高）  |                                               |
#
# 未覆盖项及原因：
# - _call_end_callbacks_on_future 的 RuntimeError 分支：需要 torch.jit.Future 对象，成本高
# - __exit__ 中 run_callbacks_on_exit=False 路径：仅由 _call_end_callbacks_on_future 设置
# - TorchScript 专用路径：标准 pytest 中无法触发

import contextlib

import pytest
import torch
import torch.autograd.profiler as profiler


# ---------------------------------------------------------------------------
# 初始化行为测试（不依赖加速卡）
# ---------------------------------------------------------------------------

class TestRecordFunctionInit:
    """验证 __init__ 阶段属性初始化正确，不依赖加速卡设备。"""

    def test_init_name_only(self):
        """仅传 name，args 默认 None，run_callbacks_on_exit 默认 True，record 初始为 None。"""
        rf = profiler.record_function("my_label")
        assert rf.name == "my_label"
        assert rf.args is None
        assert rf.run_callbacks_on_exit is True
        assert rf.record is None

    def test_init_with_args(self):
        """同时传 name 和 args，属性均正确存储。"""
        rf = profiler.record_function("my_label", args="arg1=1, arg2=2")
        assert rf.name == "my_label"
        assert rf.args == "arg1=1, arg2=2"
        assert rf.run_callbacks_on_exit is True

    def test_init_empty_string_name(self):
        """空字符串名称仍可合法初始化。"""
        rf = profiler.record_function("")
        assert rf.name == ""
        assert rf.args is None

    def test_init_special_chars_name(self):
        """含特殊字符的标签名合法初始化。"""
        rf = profiler.record_function("module/layer::forward[0]")
        assert rf.name == "module/layer::forward[0]"

    def test_inherits_context_decorator(self):
        """record_function 应继承自 contextlib.ContextDecorator。"""
        assert issubclass(profiler.record_function, contextlib.ContextDecorator)


# ---------------------------------------------------------------------------
# context manager 基本行为（依赖加速卡）
# ---------------------------------------------------------------------------

class TestRecordFunctionContextManager:
    """验证 with 语句进入/退出路径，包括 __enter__/__exit__ 的正常分支。"""

    def test_context_manager_basic(self, device):
        """最基本的 with 语句用法，仅传 name。"""
        with profiler.record_function("test_block"):
            t = torch.ones(4, device=device)
        assert t.device.type == device.type

    def test_record_attr_non_none_after_enter(self):
        """__enter__ 后 self.record 应变为非 None。"""
        rf = profiler.record_function("check_record")
        assert rf.record is None
        with rf:
            assert rf.record is not None

    def test_context_manager_with_args(self, device):
        """传 name 和 args 的 with 语句用法。"""
        with profiler.record_function("test_block_args", args="x=1"):
            t = torch.zeros(2, 3, device=device)
        assert t.shape == (2, 3)

    def test_context_manager_returns_self(self):
        """__enter__ 应返回 record_function 实例本身（支持 as 绑定）。"""
        with profiler.record_function("self_check") as rf:
            assert isinstance(rf, profiler.record_function)

    def test_context_manager_empty_name(self, device):
        """空字符串标签作为 context manager，能正常进入和退出。"""
        with profiler.record_function(""):
            t = torch.tensor(1.0, device=device)
        assert t.device.type == device.type

    def test_context_manager_special_chars(self, device):
        """含特殊字符的标签名作为 context manager。"""
        with profiler.record_function("nn.Linear::forward/step[0]"):
            t = torch.randn(3, 3, device=device)
        assert t.device.type == device.type

    def test_context_manager_none_args_explicit(self, device):
        """显式传入 args=None 与不传 args 等价。"""
        with profiler.record_function("explicit_none_args", args=None):
            t = torch.ones(2, device=device)
        assert t.device.type == device.type

    def test_run_callbacks_on_exit_true_after_normal_exit(self, device):
        """正常 with 语句退出后，run_callbacks_on_exit 保持 True。"""
        rf = profiler.record_function("callbacks_check")
        with rf:
            _ = torch.zeros(1, device=device)
        assert rf.run_callbacks_on_exit is True


# ---------------------------------------------------------------------------
# 嵌套使用（依赖加速卡）
# ---------------------------------------------------------------------------

class TestRecordFunctionNested:
    """验证嵌套 record_function 场景。"""

    def test_nested_context_manager(self, device):
        """两层嵌套，内外层均正常退出。"""
        with profiler.record_function("outer"):
            t = torch.randn(2, 2, device=device)
            with profiler.record_function("inner"):
                t2 = t * 2
        assert t2.device.type == device.type

    def test_triple_nested(self, device):
        """三层嵌套，所有层均正常退出。"""
        with profiler.record_function("level1"):
            with profiler.record_function("level2"):
                with profiler.record_function("level3"):
                    t = torch.ones(1, device=device)
        assert t.device.type == device.type

    def test_nested_with_args(self, device):
        """嵌套场景中混合传 args 与不传 args。"""
        with profiler.record_function("outer_label"):
            with profiler.record_function("inner_label", args="batch=32"):
                t = torch.zeros(32, 10, device=device)
        assert t.shape == (32, 10)

    def test_sequential_blocks(self, device):
        """多个连续的 record_function block。"""
        t = torch.randn(8, device=device)
        with profiler.record_function("block_a"):
            t1 = t * 2
        with profiler.record_function("block_b"):
            t2 = t + 1
        assert t1.device.type == device.type
        assert t2.device.type == device.type


# ---------------------------------------------------------------------------
# 在加速卡 tensor 操作上下文中使用
# ---------------------------------------------------------------------------

class TestRecordFunctionWithDeviceOps:
    """在真实加速卡 tensor 操作中使用 record_function。"""

    def test_with_matmul(self, device):
        """在矩阵乘法操作周围添加标签。"""
        a = torch.randn(4, 8, device=device)
        b = torch.randn(8, 4, device=device)
        with profiler.record_function("matmul_block"):
            c = torch.mm(a, b)
        assert c.shape == (4, 4)
        assert c.device.type == device.type

    def test_with_autograd(self, device):
        """在包含反向传播的代码块上添加标签。"""
        x = torch.randn(3, 3, device=device, requires_grad=True)
        with profiler.record_function("forward_pass"):
            y = (x ** 2).sum()
        y.backward()
        assert x.grad is not None
        assert x.grad.device.type == device.type

    def test_inside_profiler_profile(self, device):
        """在 profiler.profile() 内部使用 record_function，验证标签出现在事件列表中。"""
        x = torch.randn(2, 2, device=device)
        label = "labeled_block"
        with profiler.profile() as prof:
            with profiler.record_function(label):
                _ = x + x
        event_names = [e.name for e in prof.function_events]
        assert label in event_names

    def test_with_large_tensor(self, device):
        """在较大 tensor 操作上添加标签。"""
        with profiler.record_function("large_tensor_block"):
            t = torch.randn(128, 256, device=device)
            result = t.sum(dim=-1)
        assert result.shape == (128,)
        assert result.device.type == device.type


# ---------------------------------------------------------------------------
# 作为函数装饰器使用（contextlib.ContextDecorator 继承）
# ---------------------------------------------------------------------------

class TestRecordFunctionDecorator:
    """验证 record_function 作为 @decorator 使用。"""

    def test_as_decorator_basic(self, device):
        """作为装饰器标注函数，调用时不抛异常，返回值正确。"""
        @profiler.record_function("decorated_fn")
        def my_fn():
            return torch.ones(3, device=device)

        result = my_fn()
        assert result.device.type == device.type
        assert result.shape == (3,)

    def test_as_decorator_with_args(self, device):
        """带 args 的装饰器用法。"""
        @profiler.record_function("decorated_with_args", args="param=42")
        def compute(x):
            return x * 2

        t = torch.randn(4, device=device)
        result = compute(t)
        assert result.device.type == device.type
        assert result.shape == (4,)

    def test_as_decorator_multiple_calls(self, device):
        """被装饰函数多次调用，每次均能正常进入和退出 context。"""
        call_count = []

        @profiler.record_function("multi_call_fn")
        def fn():
            call_count.append(1)
            return torch.zeros(2, device=device)

        fn()
        fn()
        fn()
        assert len(call_count) == 3

    def test_as_decorator_with_arguments_to_function(self, device):
        """被装饰函数接受参数，装饰器不影响参数传递。"""
        @profiler.record_function("fn_with_params")
        def add_tensors(a, b):
            return a + b

        x = torch.ones(3, device=device)
        y = torch.ones(3, device=device) * 2
        result = add_tensors(x, y)
        assert result.device.type == device.type
        assert result.shape == (3,)
