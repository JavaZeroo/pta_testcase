"""
测试目的：
1. 验证 torch.fx.node.has_side_effect 对不同 callable 的注册行为是否符合预期。
2. 验证已注册目标在 FX 节点上的 impurity 判定结果与 has_side_effect 的注册效果一致。
3. 验证缺参、不可哈希入参等异常场景可被 pytest.raises 捕获。

API 名称：torch.fx.node.has_side_effect

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 参数是否传入 | 已覆盖 | 传入正常参数；不传入时触发 TypeError |
| 主要 callable 类型 | 已覆盖 | Python 函数、lambda、内置函数/方法、可调用对象、partial、框架内置函数 |
| 主要类型 | 已覆盖 | callable 类型、list/dict 等不可哈希类型 |
| 正常 / 异常 / 边界 | 已覆盖 | 正常注册、缺参异常、不可哈希异常 |
| device 语义 | 已说明 | 该 API 仅维护 FX 副作用注册表，不依赖具体 device；使用普通 Tensor 仅用于构造部分 callable 入参 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 多 device / 分布式场景 | 该 API 仅维护 FX 副作用注册表，与具体 device 或分布式调度无关 |
| 上层 FX 编译/优化删除行为 | 属于更上层图优化逻辑，不是 has_side_effect 的直接职责 |
| 返回值布尔语义 | 该 API 的真实返回值是原函数对象，而不是 bool；因此只验证注册效果，不验证错误的布尔假设 |
"""

import functools
import math
import warnings

import pytest

import torch

import torch.fx.node as fxnode


@pytest.fixture()
def base_tensor():
    return torch.tensor([1.0, 2.0])


def _make_call_function_node(target, args=(), kwargs=None):
    graph = torch.fx.Graph()
    graph.placeholder("x")
    if kwargs is None:
        kwargs = {}
    return graph.create_node("call_function", target, args=args, kwargs=kwargs, name="side_effect_node")


def _sample_side_effect_fn(x):
    return x


class _CallableWrapper:
    def __call__(self, x):
        return x


def test_has_side_effect_missing_required_argument_raises_type_error(base_tensor):
    """验证 has_side_effect 缺少必填参数时会抛出 TypeError。"""
    assert base_tensor.device.type == "cpu"

    with pytest.raises(TypeError):
        fxnode.has_side_effect()


@pytest.mark.parametrize(
    "case",
    [
        "custom_fn",
        "lambda",
        "print",
        "warn",
        "torch_assert",
        "partial",
        "callable_object",
        "bound_method",
    ],
)
def test_has_side_effect_registers_callable_variants_and_marks_impure(base_tensor, case):
    """验证不同 callable 类型在注册后可使对应 FX Node 判定为 impurity。"""
    assert base_tensor.device.type == "cpu"

    value = base_tensor + 1
    assert value.device.type == "cpu"

    if case == "custom_fn":
        target = _sample_side_effect_fn
        node_args = (value,)
        node_kwargs = {}
    elif case == "lambda":
        target = lambda x: x
        node_args = (value,)
        node_kwargs = {}
    elif case == "print":
        target = print
        node_args = ("side-effect",)
        node_kwargs = {}
    elif case == "warn":
        target = warnings.warn
        node_args = ("side-effect",)
        node_kwargs = {}
    elif case == "torch_assert":
        target = torch._assert
        node_args = (True, "assert msg")
        node_kwargs = {}
    elif case == "partial":
        target = functools.partial(_sample_side_effect_fn)
        node_args = (value,)
        node_kwargs = {}
    elif case == "callable_object":
        target = _CallableWrapper()
        node_args = (value,)
        node_kwargs = {}
    else:
        target = base_tensor.add
        node_args = (1,)
        node_kwargs = {}

    assert callable(target)

    registered_fn = fxnode.has_side_effect(target)
    assert registered_fn is target

    node = _make_call_function_node(target, args=node_args, kwargs=node_kwargs)
    result = node.is_impure()

    assert isinstance(result, bool)
    assert result is True


@pytest.mark.parametrize(
    "bad_value",
    [
        [],
        {},
    ],
)
def test_has_side_effect_unhashable_input_raises_type_error(base_tensor, bad_value):
    """验证 list/dict 等不可哈希入参会触发 TypeError。"""
    assert base_tensor.device.type == "cpu"

    with pytest.raises(TypeError):
        fxnode.has_side_effect(bad_value)


@pytest.mark.parametrize(
    "case",
    [
        "torch_add",
        "sqrt",
    ],
)
def test_has_side_effect_does_not_change_unregistered_pure_callables(base_tensor, case):
    """验证未注册的普通 callable 仍然保持 FX 纯函数节点语义。"""
    assert base_tensor.device.type == "cpu"

    other_tensor = base_tensor + 2
    assert other_tensor.device.type == "cpu"

    if case == "torch_add":
        target = torch.add
        node_args = (base_tensor, other_tensor)
        node_kwargs = {}
    else:
        target = math.sqrt
        node_args = (4.0,)
        node_kwargs = {}

    assert callable(target)

    node = _make_call_function_node(target, args=node_args, kwargs=node_kwargs)
    result = node.is_impure()

    assert isinstance(result, bool)
    assert result is False
