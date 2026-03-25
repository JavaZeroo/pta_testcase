"""
测试目的：验证 torch.utils._python_dispatch.is_traceable_wrapper_subclass 在 NPU 场景下的
接口可调用性、参数处理、类型判定与异常行为。

API 名称：torch.utils._python_dispatch.is_traceable_wrapper_subclass

覆盖参数维度表：
| 维度 | 覆盖场景 | 期望 |
| --- | --- | --- |
| 1. 传参 / 不传参 | 传入 1 个参数、缺少参数、传入多余参数 | 正常返回 / TypeError |
| 2. None / 非 None | None、普通对象、容器、标量、字符串 | False |
| 3. 主要类型 | NPU 普通张量、traceable wrapper subclass、non-traceable wrapper subclass、仅 flatten、仅 unflatten | False / True |
| 4. 设备维度 | 所有张量对象均在 NPU 上构造 | 结果符合预期 |
| 5. 异常场景 | 缺参、超参、错误关键字参数 | pytest.raises(TypeError) |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| torch.compile 下的真实 tracing、图生成与 aliasing 语义 | 本用例聚焦于该 API 的纯判定逻辑与入参边界；相关编译链路属于更高层集成验证，不适合作为本文件的单元级断言重点。 |
| 更复杂的自定义 Tensor 子类层级组合 | 当前已覆盖该 API 依赖的关键分支：普通张量、完整 wrapper subclass、部分 magic method 子类与非 tensor 输入，足以验证接口判定逻辑。 |
"""

import pytest

import torch

try:
    import torch_npu  # noqa: F401
except ImportError:
    pytest.skip("torch_npu is not installed in the current environment.", allow_module_level=True)

try:
    import torch.utils._python_dispatch as _python_dispatch
except ImportError:
    pytest.skip(
        "torch.utils._python_dispatch is unavailable in the current torch version.",
        allow_module_level=True,
    )

if not hasattr(_python_dispatch, "is_traceable_wrapper_subclass"):
    pytest.skip(
        "torch.utils._python_dispatch.is_traceable_wrapper_subclass is unavailable in the current torch version.",
        allow_module_level=True,
    )

from torch.utils._python_dispatch import is_traceable_wrapper_subclass

try:
    import torch.utils._pytree as _pytree
except ImportError:
    pytest.skip(
        "torch.utils._pytree is unavailable in the current torch version.",
        allow_module_level=True,
    )

if not hasattr(_pytree, "tree_map_only"):
    pytest.skip(
        "torch.utils._pytree.tree_map_only is unavailable in the current torch version.",
        allow_module_level=True,
    )

from torch.utils._pytree import tree_map_only


def _wrapper_torch_dispatch(wrapper_cls, func, args, kwargs=None):
    if kwargs is None:
        kwargs = {}

    def unwrap(x):
        return x.elem if isinstance(x, wrapper_cls) else x

    def wrap(x):
        return wrapper_cls(x) if isinstance(x, torch.Tensor) else x

    return tree_map_only(torch.Tensor, wrap, func(*tree_map_only(wrapper_cls, unwrap, args), **tree_map_only(wrapper_cls, unwrap, kwargs)))


@pytest.fixture(scope="module", autouse=True)
def _require_npu_backend():
    if not hasattr(torch, "npu") or not torch.npu.is_available():
        pytest.skip("当前环境缺少可用的 NPU 后端，无法执行基于 NPU 的功能测试。")


class TraceableWrapperTensor(torch.Tensor):
    @staticmethod
    def __new__(cls, elem):
        return torch.Tensor._make_subclass(cls, elem, elem.requires_grad)

    def __init__(self, elem):
        self.elem = elem

    @classmethod
    def __torch_dispatch__(cls, func, types, args=(), kwargs=None):
        return _wrapper_torch_dispatch(cls, func, args, kwargs)

    def __tensor_flatten__(self):
        return ["elem"], {"kind": "traceable_wrapper"}

    @classmethod
    def __tensor_unflatten__(cls, inner_tensors, metadata, outer_size, outer_stride):
        return cls(inner_tensors["elem"])


class NonTraceableWrapperTensor(torch.Tensor):
    @staticmethod
    def __new__(cls, elem):
        return torch.Tensor._make_subclass(cls, elem, elem.requires_grad)

    def __init__(self, elem):
        self.elem = elem

    @classmethod
    def __torch_dispatch__(cls, func, types, args=(), kwargs=None):
        return _wrapper_torch_dispatch(cls, func, args, kwargs)


class FlattenOnlyWrapperTensor(torch.Tensor):
    @staticmethod
    def __new__(cls, elem):
        return torch.Tensor._make_subclass(cls, elem, elem.requires_grad)

    def __init__(self, elem):
        self.elem = elem

    @classmethod
    def __torch_dispatch__(cls, func, types, args=(), kwargs=None):
        return _wrapper_torch_dispatch(cls, func, args, kwargs)

    def __tensor_flatten__(self):
        return ["elem"], {"kind": "flatten_only"}


class UnflattenOnlyWrapperTensor(torch.Tensor):
    @staticmethod
    def __new__(cls, elem):
        return torch.Tensor._make_subclass(cls, elem, elem.requires_grad)

    def __init__(self, elem):
        self.elem = elem

    @classmethod
    def __torch_dispatch__(cls, func, types, args=(), kwargs=None):
        return _wrapper_torch_dispatch(cls, func, args, kwargs)

    @classmethod
    def __tensor_unflatten__(cls, inner_tensors, metadata, outer_size, outer_stride):
        return cls(inner_tensors["elem"])


def _make_npu_tensor(shape=(2, 3), *, requires_grad=False):
    return torch.ones(shape, device="npu", requires_grad=requires_grad)


@pytest.mark.parametrize(
    "value",
    [
        None,
        0,
        3.14,
        "",
        [],
        {},
        object(),
    ],
)
def test_is_traceable_wrapper_subclass_non_tensor_inputs_return_false(value):
    result = is_traceable_wrapper_subclass(value)

    assert isinstance(result, bool)
    assert result is False


def test_is_traceable_wrapper_subclass_regular_npu_tensor_returns_false():
    assert callable(is_traceable_wrapper_subclass)

    tensor = _make_npu_tensor()

    result = is_traceable_wrapper_subclass(tensor)

    assert isinstance(result, bool)
    assert result is False


def test_is_traceable_wrapper_subclass_regular_npu_scalar_tensor_returns_false():
    tensor = torch.tensor(7, device="npu")

    result = is_traceable_wrapper_subclass(tensor)

    assert isinstance(result, bool)
    assert result is False


@pytest.mark.parametrize(
    "wrapper_cls, expected",
    [
        (TraceableWrapperTensor, True),
        (NonTraceableWrapperTensor, False),
        (FlattenOnlyWrapperTensor, False),
        (UnflattenOnlyWrapperTensor, False),
    ],
)
def test_is_traceable_wrapper_subclass_wrapper_tensor_classification(wrapper_cls, expected):
    base = _make_npu_tensor(shape=(4,), requires_grad=True)
    tensor = wrapper_cls(base)

    result = is_traceable_wrapper_subclass(tensor)

    assert isinstance(result, bool)
    assert result is expected


def test_is_traceable_wrapper_subclass_traceable_wrapper_with_other_shape_still_true():
    base = _make_npu_tensor(shape=(1, 2, 3))
    tensor = TraceableWrapperTensor(base)

    result = is_traceable_wrapper_subclass(tensor)

    assert isinstance(result, bool)
    assert result is True


def test_is_traceable_wrapper_subclass_no_arguments_raises_type_error():
    with pytest.raises(TypeError):
        is_traceable_wrapper_subclass()


def test_is_traceable_wrapper_subclass_too_many_arguments_raises_type_error():
    tensor = _make_npu_tensor(shape=(1,))

    with pytest.raises(TypeError):
        is_traceable_wrapper_subclass(tensor, tensor)


def test_is_traceable_wrapper_subclass_unexpected_keyword_raises_type_error():
    tensor = _make_npu_tensor(shape=(1,))

    with pytest.raises(TypeError):
        is_traceable_wrapper_subclass(tensor, unexpected=True)
