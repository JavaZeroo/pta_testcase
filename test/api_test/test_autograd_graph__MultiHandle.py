"""
测试目的：
1. 验证 torch.autograd.graph._MultiHandle 在当前环境中可访问、可实例化，并且支持 isinstance 识别。
2. 验证其能够包装多个由 NPU Tensor.register_hook 返回的 RemovableHandle，并通过 remove() 一次性移除全部 hook。
3. 验证 __getstate__/__setstate__ 的状态转移能力，覆盖空 tuple、None、缺省参数与异常场景。

API 名称：torch.autograd.graph._MultiHandle

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| API 可访问性 | 已覆盖 | 检查 torch.autograd.graph._MultiHandle 属性存在、可实例化、isinstance 判断正确 |
| handles = 多个 RemovableHandle | 已覆盖 | 使用 NPU Tensor.register_hook 生成多个 handle 并构造 _MultiHandle |
| handles = 空 tuple | 已覆盖 | 验证空 handles 下 remove() 为 no-op，__getstate__ 可返回空 tuple |
| handles = None | 已覆盖 | 验证构造后调用 remove() 会抛出 TypeError |
| handles 不传 | 已覆盖 | 验证缺少必需参数时抛出 TypeError |
| __getstate__ / __setstate__ | 已覆盖 | 验证状态可正确导出/回填，且回填后仍可 remove() |
| NPU Tensor | 已覆盖 | hook 注册、反向传播、移除行为均在 NPU 上执行 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| list/其他可迭代 handles 输入 | 当前仅覆盖官方签名声明的 tuple 路径，避免依赖未显式保证的宽松入参行为 |
| 多卡 NPU 场景 | 仅依赖单卡即可验证该内部 API 的主要功能 |
| hook 回调的数值梯度正确性 | 测试重点是 hook 的注册、包装与移除，不做具体数值比对 |
"""

import pytest

import torch
import torch_npu  # noqa: F401
from torch.autograd import graph as autograd_graph


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 _MultiHandle 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 _MultiHandle 测试。")


def _require_multihandle_cls():
    _require_npu()
    if not hasattr(autograd_graph, "_MultiHandle"):
        pytest.skip("当前 PyTorch 版本未提供 torch.autograd.graph._MultiHandle，无法执行测试。")
    return autograd_graph._MultiHandle


def _make_npu_leaf_tensors():
    _require_npu()
    x1 = torch.tensor([1.0, 2.0], device=torch.device("npu:0"), requires_grad=True)
    x2 = torch.tensor([3.0, 4.0], device=torch.device("npu:0"), requires_grad=True)
    return x1, x2


@pytest.fixture()
def multihandle_cls():
    return _require_multihandle_cls()


@pytest.fixture()
def npu_leaf_tensors():
    return _make_npu_leaf_tensors()


def test_multihandle_import_accessibility_class_exists_and_isinstance(multihandle_cls):
    """验证模块属性可访问、类存在、且实例类型判断正确。"""
    mh = multihandle_cls(())

    assert hasattr(autograd_graph, "_MultiHandle")
    assert callable(multihandle_cls)
    assert isinstance(mh, multihandle_cls)
    assert mh.handles == ()
    assert mh.__getstate__() == ()


def test_multihandle_construct_from_multiple_removable_handles_and_remove_all_hooks(
    multihandle_cls, npu_leaf_tensors
):
    """验证多个 NPU hook handle 可被包装，并且 remove() 会移除全部 hook。"""
    x1, x2 = npu_leaf_tensors
    hook_counts = {"h1": 0, "h2": 0}

    def hook1(grad):
        hook_counts["h1"] += 1
        return grad

    def hook2(grad):
        hook_counts["h2"] += 1
        return grad

    handle1 = x1.register_hook(hook1)
    handle2 = x2.register_hook(hook2)
    mh = multihandle_cls((handle1, handle2))

    assert isinstance(mh, multihandle_cls)
    assert len(mh.handles) == 2
    assert mh.__getstate__() == (handle1, handle2)

    loss = (x1 + x2).sum()
    loss.backward()

    assert hook_counts == {"h1": 1, "h2": 1}

    x1.grad = None
    x2.grad = None
    mh.remove()

    loss2 = (x1 + x2).sum()
    loss2.backward()

    assert hook_counts == {"h1": 1, "h2": 1}


def test_multihandle_getstate_setstate_roundtrip_and_remove(multihandle_cls, npu_leaf_tensors):
    """验证 __getstate__/__setstate__ 能导出并回填句柄状态。"""
    x1, x2 = npu_leaf_tensors
    hook_counts = {"h1": 0, "h2": 0}

    def hook1(grad):
        hook_counts["h1"] += 1
        return grad

    def hook2(grad):
        hook_counts["h2"] += 1
        return grad

    handle1 = x1.register_hook(hook1)
    handle2 = x2.register_hook(hook2)
    original = multihandle_cls((handle1, handle2))
    state = original.__getstate__()

    restored = multihandle_cls(tuple())
    restored.__setstate__(state)

    assert restored.handles == state
    assert isinstance(restored, multihandle_cls)

    loss = (x1 + x2).sum()
    loss.backward()
    assert hook_counts == {"h1": 1, "h2": 1}

    x1.grad = None
    x2.grad = None
    restored.remove()

    loss2 = (x1 + x2).sum()
    loss2.backward()
    assert hook_counts == {"h1": 1, "h2": 1}


def test_multihandle_empty_handle_tuple_behavior(multihandle_cls):
    """验证空 handles 边界下对象可构造且 remove() 为 no-op。"""
    mh = multihandle_cls(tuple())

    assert isinstance(mh, multihandle_cls)
    assert mh.handles == tuple()
    assert mh.__getstate__() == tuple()

    mh.remove()
    assert mh.handles == tuple()


def test_multihandle_missing_argument_raises_typeerror(multihandle_cls):
    """验证构造时未传 handles 会抛出 TypeError。"""
    with pytest.raises(TypeError):
        multihandle_cls()


def test_multihandle_none_handles_raise_on_remove(multihandle_cls):
    """验证 handles=None 时，remove() 迭代 handles 会抛出 TypeError。"""
    mh = multihandle_cls(None)

    with pytest.raises(TypeError):
        mh.remove()


def test_multihandle_handles_with_invalid_element_raise_on_remove(multihandle_cls):
    """验证 handles 中包含非 RemovableHandle 元素时，remove() 会抛出 AttributeError。"""
    mh = multihandle_cls((object(),))

    with pytest.raises(AttributeError):
        mh.remove()


@pytest.mark.parametrize(
    "state, expected_exception",
    [
        (None, TypeError),
        ((object(),), AttributeError),
    ],
)
def test_multihandle_setstate_invalid_state_raises_on_remove(
    multihandle_cls, state, expected_exception
):
    """验证 __setstate__ 接收非法状态后，remove() 会在使用该状态时抛出相应异常。"""
    mh = multihandle_cls(tuple())
    mh.__setstate__(state)

    with pytest.raises(expected_exception):
        mh.remove()
