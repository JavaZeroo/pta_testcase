# 测试目的：验证 torch.autograd.profiler.record_function 在 NPU 上的基本功能行为
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
# 1. __init__: 初始化 name、args、run_callbacks_on_exit=True、record=None（通过 torch.jit.annotate）
#    → test_init_name_only, test_init_with_args, test_init_empty_string_name
# 2. __enter__: 调用 torch.ops.profiler._record_function_enter_new(name, args)，record 变非 None，返回 self
#    → test_record_attr_non_none_after_enter, test_context_manager_returns_self
# 3. __exit__ 分支 A: run_callbacks_on_exit=False → 直接 return，跳过 exit 回调
#    → 由 _call_end_callbacks_on_future 设置，不在此直接测试（需要 JIT Future）
# 4. __exit__ 分支 B: run_callbacks_on_exit=True → 调用 _record_function_exit 清理 record
#    → test_context_manager_basic（with 语句自动触发 __exit__）
# 5. _call_end_callbacks_on_future 首次调用：设置 run_callbacks_on_exit=False，挂载 future 回调
#    → 不测试（需要 torch.jit.Future，NPU 场景构造成本高）
# 6. _call_end_callbacks_on_future 二次调用：run_callbacks_on_exit 已为 False → raise RuntimeError
#    → 不测试（前提条件 5 无法简单满足）
# 7. 作为装饰器（contextlib.ContextDecorator 继承）
#    → test_as_decorator_basic, test_as_decorator_with_args, test_as_decorator_multiple_calls
#
# 覆盖维度：
#
# | 覆盖维度                  | 说明                                              | 覆盖情况                                                     |
# |---------------------------|---------------------------------------------------|--------------------------------------------------------------|
# | 空/非空（None 或其他值）  | args=None 与 args 非 None 两条路径                | 已覆盖：test_init_name_only / test_init_with_args            |
# | 枚举选项                  | N/A（无枚举型入参）                               | N/A                                                          |
# | 参数类型                  | name: str；args: Optional[str]                    | 已覆盖：str / None                                           |
# | 传参与不传参              | args 可选，覆盖传入与使用默认值两种情形           | 已覆盖                                                       |
# | 等价类/边界值             | 空字符串名称、含特殊字符名称、嵌套 context       | 已覆盖                                                       |
# | 正常传参场景              | with 语句、装饰器、嵌套、NPU tensor 操作中使用   | 已覆盖                                                       |
# | 异常传参场景              | 仅覆盖有明确证据的异常                            | 不覆盖（_call_end_callbacks_on_future 需要 JIT Future，成本高）|
#
# 未覆盖项及原因：
# - _call_end_callbacks_on_future 的 RuntimeError 分支：需要 torch.jit.Future 对象，
#   在非 TorchScript 环境下构造成本高，且与 NPU 功能验证关联度低，故省略。
# - __exit__ 中 run_callbacks_on_exit=False 路径：仅由 _call_end_callbacks_on_future 设置，
#   不单独构造。
# - __exit__ 中 torch.jit.is_scripting() 为 True 的 else 分支：TorchScript 专用路径，
#   标准 pytest 中无法触发，省略。
# - _call_end_callbacks_on_future 中 torch.jit.is_scripting() 为 True 的 else 分支：同上。

import contextlib

import pytest
import torch
import torch.autograd.profiler as profiler
try:
    import torch_npu  # noqa: F401
except ImportError:
    pytest.skip("torch_npu not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _npu_available() -> bool:
    try:
        return torch.npu.is_available()
    except AttributeError:
        return False


# ---------------------------------------------------------------------------
# 初始化行为测试（不依赖 NPU）
# ---------------------------------------------------------------------------

class TestRecordFunctionInit:
    """验证 __init__ 阶段属性初始化正确，不依赖 NPU 设备。"""

    def test_init_name_only(self):
        """仅传 name，args 默认 None，run_callbacks_on_exit 默认 True，record 初始为 None。"""
        rf = profiler.record_function("my_label")
        assert rf.name == "my_label"
        assert rf.args is None
        assert rf.run_callbacks_on_exit is True
        # record 在 __enter__ 之前应为 None
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
# context manager 基本行为（依赖 NPU）
# ---------------------------------------------------------------------------

class TestRecordFunctionContextManager:
    """验证 with 语句进入/退出路径，包括 __enter__/__exit__ 的正常分支。"""

    def test_context_manager_basic(self):
        """最基本的 with 语句用法，仅传 name，不依赖 profiler.profile()。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function("test_block"):
            t = torch.ones(4, device="npu")
        # 正常退出即可，不抛异常则通过
        assert t.device.type == "npu"

    def test_record_attr_non_none_after_enter(self):
        """__enter__ 后 self.record 应变为非 None（_record_function_enter_new 的返回值）。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        rf = profiler.record_function("check_record")
        assert rf.record is None
        with rf:
            assert rf.record is not None

    def test_context_manager_with_args(self):
        """传 name 和 args 的 with 语句用法，args 字符串传递给底层函数。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function("test_block_args", args="x=1"):
            t = torch.zeros(2, 3, device="npu")
        assert t.shape == (2, 3)

    def test_context_manager_returns_self(self):
        """__enter__ 应返回 record_function 实例本身（支持 as 绑定）。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function("self_check") as rf:
            assert isinstance(rf, profiler.record_function)

    def test_context_manager_empty_name(self):
        """空字符串标签作为 context manager，能正常进入和退出。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function(""):
            t = torch.tensor(1.0, device="npu")
        assert t.device.type == "npu"

    def test_context_manager_special_chars(self):
        """含特殊字符的标签名作为 context manager，底层不应拒绝。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function("nn.Linear::forward/step[0]"):
            t = torch.randn(3, 3, device="npu")
        assert t.device.type == "npu"

    def test_context_manager_none_args_explicit(self):
        """显式传入 args=None 与不传 args 等价，均可正常使用。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function("explicit_none_args", args=None):
            t = torch.ones(2, device="npu")
        assert t.device.type == "npu"

    def test_run_callbacks_on_exit_true_after_normal_exit(self):
        """正常 with 语句退出后，run_callbacks_on_exit 保持 True（未被改变）。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        rf = profiler.record_function("callbacks_check")
        with rf:
            _ = torch.zeros(1, device="npu")
        # run_callbacks_on_exit 在 __exit__ 中未被修改，应保持 True
        assert rf.run_callbacks_on_exit is True


# ---------------------------------------------------------------------------
# 嵌套使用（依赖 NPU）
# ---------------------------------------------------------------------------

class TestRecordFunctionNested:
    """验证嵌套 record_function 场景，多个 context manager 堆叠。"""

    def test_nested_context_manager(self):
        """两层嵌套，内外层均正常退出。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function("outer"):
            t = torch.randn(2, 2, device="npu")
            with profiler.record_function("inner"):
                t2 = t * 2
        assert t2.device.type == "npu"

    def test_triple_nested(self):
        """三层嵌套，所有层均正常退出，验证不相互干扰。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function("level1"):
            with profiler.record_function("level2"):
                with profiler.record_function("level3"):
                    t = torch.ones(1, device="npu")
        assert t.device.type == "npu"

    def test_nested_with_args(self):
        """嵌套场景中混合传 args 与不传 args，各层独立运作。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function("outer_label"):
            with profiler.record_function("inner_label", args="batch=32"):
                t = torch.zeros(32, 10, device="npu")
        assert t.shape == (32, 10)

    def test_sequential_blocks(self):
        """多个连续的 record_function block，验证退出后可再次进入新 block。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        t = torch.randn(8, device="npu")
        with profiler.record_function("block_a"):
            t1 = t * 2
        with profiler.record_function("block_b"):
            t2 = t + 1
        assert t1.device.type == "npu"
        assert t2.device.type == "npu"


# ---------------------------------------------------------------------------
# 在 NPU tensor 操作上下文中使用
# ---------------------------------------------------------------------------

class TestRecordFunctionWithNpuOps:
    """在真实 NPU tensor 操作中使用 record_function，验证不干扰计算结果。"""

    def test_with_matmul(self):
        """在矩阵乘法操作周围添加标签，结果形状和设备正确。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        a = torch.randn(4, 8, device="npu")
        b = torch.randn(8, 4, device="npu")
        with profiler.record_function("matmul_block"):
            c = torch.mm(a, b)
        assert c.shape == (4, 4)
        assert c.device.type == "npu"

    def test_with_autograd(self):
        """在包含反向传播的代码块上添加标签，梯度仍在 NPU 上。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        x = torch.randn(3, 3, device="npu", requires_grad=True)
        with profiler.record_function("forward_pass"):
            y = (x ** 2).sum()
        y.backward()
        assert x.grad is not None
        assert x.grad.device.type == "npu"

    def test_inside_profiler_profile(self):
        """在 profiler.profile() 内部使用 record_function，验证标签出现在事件列表中。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        x = torch.randn(2, 2, device="npu")
        label = "npu_labeled_block"
        with profiler.profile() as prof:
            with profiler.record_function(label):
                _ = x + x
        event_names = [e.name for e in prof.function_events]
        assert label in event_names

    def test_with_large_tensor(self):
        """在较大 tensor 操作上添加标签，block 正常退出。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")
        with profiler.record_function("large_tensor_block"):
            t = torch.randn(128, 256, device="npu")
            result = t.sum(dim=-1)
        assert result.shape == (128,)
        assert result.device.type == "npu"


# ---------------------------------------------------------------------------
# 作为函数装饰器使用（contextlib.ContextDecorator 继承）
# ---------------------------------------------------------------------------

class TestRecordFunctionDecorator:
    """验证 record_function 作为 @decorator 使用，覆盖装饰器路径。"""

    def test_as_decorator_basic(self):
        """作为装饰器标注函数，调用时不抛异常，返回值正确。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")

        @profiler.record_function("decorated_fn")
        def my_fn():
            return torch.ones(3, device="npu")

        result = my_fn()
        assert result.device.type == "npu"
        assert result.shape == (3,)

    def test_as_decorator_with_args(self):
        """带 args 的装饰器用法，操作正常完成。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")

        @profiler.record_function("decorated_with_args", args="param=42")
        def compute(x):
            return x * 2

        t = torch.randn(4, device="npu")
        result = compute(t)
        assert result.device.type == "npu"
        assert result.shape == (4,)

    def test_as_decorator_multiple_calls(self):
        """被装饰函数多次调用，每次均能正常进入和退出 context。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")

        call_count = []

        @profiler.record_function("multi_call_fn")
        def fn():
            call_count.append(1)
            return torch.zeros(2, device="npu")

        fn()
        fn()
        fn()
        assert len(call_count) == 3

    def test_as_decorator_with_arguments_to_function(self):
        """被装饰函数接受参数，装饰器不影响参数传递。"""
        if not _npu_available():
            pytest.skip("NPU 不可用")

        @profiler.record_function("fn_with_params")
        def add_tensors(a, b):
            return a + b

        x = torch.ones(3, device="npu")
        y = torch.ones(3, device="npu") * 2
        result = add_tensors(x, y)
        assert result.device.type == "npu"
        assert result.shape == (3,)
