# 测试目的：验证 torch.fx.node.has_side_effect 在加速卡环境下的功能行为。
# API 名称：torch.fx.node.has_side_effect
#
# 覆盖参数维度：
#
# | 覆盖维度           | 说明                                                     | 覆盖情况                                              |
# |--------------------|----------------------------------------------------------|-------------------------------------------------------|
# | 空/非空            | fn 必须为 Callable，无 None 路径（源码无 None 判断）     | 仅覆盖非空 Callable                                   |
# | 枚举选项           | N/A（无枚举参数）                                        | N/A                                                   |
# | 参数类型           | fn 可为普通函数、lambda、含加速卡 tensor 操作的函数      | 覆盖普通函数、lambda、加速卡 tensor 操作函数          |
# | 传参与不传参       | fn 为必填参数，无可选参数                                | 覆盖必填参数传入                                      |
# | 等价类/边界值      | 同一函数重复注册、多个不同函数注册                       | 覆盖重复注册、多函数注册                              |
# | 正常传参场景       | 合法 Callable 传入后 API 可正常调用并返回原函数          | 覆盖装饰器用法、直接调用用法、返回值验证              |
# | 异常传参场景       | 无明确证据表明 API 对非法输入抛出异常，不生成异常测试    | 不覆盖                                                |
#
# 源码分支分析（torch/fx/node.py）：
#   1. _side_effectful_functions.add(fn)  → 将 fn 加入副作用函数集合
#   2. return fn                           → 返回原 fn（装饰器模式）
#   合计 2 个操作，无条件分支，全部覆盖。
#
# 未覆盖项说明：
#   - 未覆盖 fn=None 或非 Callable 的情况：源码未做类型校验，Python set.add() 接受任意对象，
#     无法预测其是否稳定抛出异常，故不生成相关负例。
#   - 未覆盖 FX trace + 完整 DCE 集成测试中加速卡算子的 IR 节点存活：
#     FX symbolic trace 在加速卡 tensor 直接操作时可能遇到 tracer 兼容问题，
#     此部分依赖 torch.fx.symbolic_trace，超出本 API 单元测试范围。

import pytest

import torch
import torch.fx
from torch.fx.node import has_side_effect, _side_effectful_functions


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _make_device_tensor(device):
    return torch.tensor([1.0, 2.0, 3.0], device=device)


# ─────────────────────────────────────────────────────────────────────────────
# 测试：装饰器用法 —— 被装饰函数返回值为原函数本身
# ─────────────────────────────────────────────────────────────────────────────

class TestHasSideEffectAsDecorator:
    def test_decorator_returns_same_function(self):
        """用作装饰器时，返回值是被装饰函数本身。"""
        def my_func():
            pass

        result = has_side_effect(my_func)
        assert result is my_func

    def test_decorated_function_is_callable(self):
        """被装饰函数仍然可以正常调用。"""
        @has_side_effect
        def add_one(x):
            return x + 1

        assert callable(add_one)
        assert add_one(10) == 11

    def test_decorator_syntax_returns_same_object(self):
        """使用 @has_side_effect 装饰器语法，函数对象不变。"""
        @has_side_effect
        def sample():
            return 42

        assert sample() == 42

    def test_decorator_on_lambda(self):
        """对 lambda 使用 has_side_effect，返回值仍为同一 lambda。"""
        fn = lambda x: x * 2  # noqa: E731
        result = has_side_effect(fn)
        assert result is fn
        assert callable(result)
        assert result(5) == 10


# ─────────────────────────────────────────────────────────────────────────────
# 测试：函数式调用 —— has_side_effect(fn) 直接调用
# ─────────────────────────────────────────────────────────────────────────────

class TestHasSideEffectFunctionalCall:
    def test_direct_call_returns_fn(self):
        """直接函数调用 has_side_effect(fn) 返回传入的 fn 对象。"""
        def my_fn():
            pass

        returned = has_side_effect(my_fn)
        assert returned is my_fn

    def test_direct_call_return_type_is_callable(self):
        """返回值类型为 Callable（可调用对象）。"""
        def my_fn(a, b):
            return a + b

        result = has_side_effect(my_fn)
        assert callable(result)

    def test_direct_call_on_builtin_like_function(self):
        """对普通可调用对象使用 has_side_effect，返回同一对象。"""
        class MyCallable:
            def __call__(self, x):
                return x

        obj = MyCallable()
        result = has_side_effect(obj)
        assert result is obj
        assert callable(result)


# ─────────────────────────────────────────────────────────────────────────────
# 测试：_side_effectful_functions 集合注册行为
# ─────────────────────────────────────────────────────────────────────────────

class TestSideEffectfulFunctionsRegistration:
    def test_function_added_to_set(self):
        """调用 has_side_effect 后，fn 应出现在 _side_effectful_functions 中。"""
        def unique_func_for_registration():
            pass

        has_side_effect(unique_func_for_registration)
        assert unique_func_for_registration in _side_effectful_functions

    def test_repeated_registration_is_idempotent(self):
        """同一函数多次注册，集合中仍只存在一个引用（set 特性）。"""
        def func_for_repeat():
            pass

        has_side_effect(func_for_repeat)
        size_after_first = len(_side_effectful_functions)
        has_side_effect(func_for_repeat)
        size_after_second = len(_side_effectful_functions)
        assert size_after_first == size_after_second

    def test_multiple_different_functions_all_registered(self):
        """多个不同函数分别注册后，均出现在集合中。"""
        def fn_alpha():
            pass

        def fn_beta():
            pass

        has_side_effect(fn_alpha)
        has_side_effect(fn_beta)
        assert fn_alpha in _side_effectful_functions
        assert fn_beta in _side_effectful_functions


# ─────────────────────────────────────────────────────────────────────────────
# 测试：在包含加速卡 tensor 操作的函数上使用
# ─────────────────────────────────────────────────────────────────────────────

class TestHasSideEffectWithDeviceOperations:
    def test_device_operation_function_registered(self, device):
        """对包含加速卡 tensor 操作的函数使用 has_side_effect，函数注册成功。"""
        @has_side_effect
        def device_op(t):
            return t + 1

        assert device_op in _side_effectful_functions

    def test_device_operation_function_still_callable(self, device):
        """被注册为副作用函数后，原函数仍然可以正常调用并在加速卡上运行。"""
        @has_side_effect
        def device_add(t):
            return t + 1

        x = _make_device_tensor(device)
        result = device_add(x)
        assert result is not None
        assert result.device.type == device.type

    def test_device_inplace_function_registered(self, device):
        """对原地操作函数使用 has_side_effect，函数成功注册并可调用。"""
        @has_side_effect
        def device_fill_(t, val):
            t.fill_(val)
            return t

        x = _make_device_tensor(device)
        result = device_fill_(x, 0.0)
        assert result is not None
        assert result.device.type == device.type
        assert device_fill_ in _side_effectful_functions

    def test_device_tensor_creation_function_registered(self, device):
        """对创建加速卡 tensor 的函数使用 has_side_effect，注册并调用均正常。"""
        @has_side_effect
        def make_zeros(dev):
            return torch.zeros(4, device=dev)

        result = make_zeros(device)
        assert result is not None
        assert result.device.type == device.type
        assert make_zeros in _side_effectful_functions


# ─────────────────────────────────────────────────────────────────────────────
# 测试：FX 图中 is_impure 行为（通过 Node.is_impure 验证注册效果）
# ─────────────────────────────────────────────────────────────────────────────

class TestHasSideEffectInFXGraph:
    def test_registered_function_node_is_impure(self):
        """注册为副作用的函数，在 FX 图中对应 call_function 节点的 is_impure 应为 True。"""
        @has_side_effect
        def my_side_effect_fn(x):
            return x

        graph = torch.fx.Graph()
        x = graph.placeholder("x")
        call_node = graph.call_function(my_side_effect_fn, (x,))
        graph.output(call_node)

        assert call_node.is_impure()

    def test_unregistered_function_node_is_not_impure(self):
        """未注册为副作用的函数，在 FX 图中对应 call_function 节点的 is_impure 应为 False。"""
        def pure_fn(x):
            return x

        if pure_fn in _side_effectful_functions:
            pytest.skip("pure_fn already in _side_effectful_functions, test state contaminated")

        graph = torch.fx.Graph()
        x = graph.placeholder("x")
        call_node = graph.call_function(pure_fn, (x,))
        graph.output(call_node)

        assert not call_node.is_impure()

    def test_dce_preserves_side_effect_node(self):
        """DCE 不应移除被标记为副作用的无用节点（无直接用户）。"""
        @has_side_effect
        def my_effectful_sink(x):
            pass

        graph = torch.fx.Graph()
        x = graph.placeholder("x")
        side_effect_node = graph.call_function(my_effectful_sink, (x,))
        graph.output(x)

        changed = graph.eliminate_dead_code()
        node_targets = [n.target for n in graph.nodes if n.op == "call_function"]
        assert my_effectful_sink in node_targets, (
            "has_side_effect 标记的函数节点不应被 DCE 移除"
        )
