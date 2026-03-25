"""
测试目的：
1. 验证 torch.utils._pytree.tree_flatten 在 NPU 环境下可正常调用，返回值结构正确，且 TreeSpec 可用于重建原始 pytree。
2. 覆盖 tree 参数的主要输入形态，包括单个 Tensor、包含标量的结构、list/tuple/dict、嵌套结构、包含空容器的结构、包含 None 的结构、混合类型结构；所有 tree 均包含 NPU Tensor 叶子节点。
3. 覆盖 is_leaf 参数的“未传/传入 None/传入非 None Callable”三类场景，并验证非 None 时可改变 flatten 行为。
4. 覆盖异常场景：循环引用结构触发递归异常，以及传入非 Callable 的 is_leaf 触发 TypeError，均使用 pytest.raises 捕获。

API 名称：torch.utils._pytree.tree_flatten

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| tree 输入形态 | 已覆盖 | 单个 Tensor、包含标量的结构、list、tuple、dict、嵌套结构、包含空容器的结构、包含 None 的结构、混合类型 |
| tree 中叶子类型 | 已覆盖 | NPU Tensor、Python int、str、None、tuple 作为 leaf |
| is_leaf 是否传入 | 已覆盖 | 未传入、显式传入 None、传入 Callable |
| is_leaf 取值分支 | 已覆盖 | None 分支、非 None 分支 |
| NPU Tensor 保留 | 已覆盖 | flatten 后的 Tensor leaf 保持在 NPU 上 |
| 返回值结构 | 已覆盖 | 校验返回值为 tuple，且包含 (leaves, TreeSpec)，leaves 为 list |
| TreeSpec 有效性 | 已覆盖 | 使用 spec.unflatten(leaves) 重建，并再次 flatten 验证 spec 一致 |
| 异常场景 | 已覆盖 | 循环引用触发 RecursionError，非 Callable 的 is_leaf 触发 TypeError |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 自定义 pytree 节点注册 | 当前仅验证内置常见结构的 flatten 行为，未引入额外自定义注册逻辑 |
| 超大规模/超深层 pytree | 为保持测试稳定性和执行时间，未构造大规模递归输入 |
| 数值正确性校验 | 该 API 关注结构展开与重建，不做叶子数值内容正确性比对 |
"""

import pytest

import torch
import torch_npu  # noqa: F401

from torch.utils import _pytree


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 tree_flatten 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 tree_flatten 测试。")


@pytest.fixture(scope="module")
def npu_tensors():
    _require_npu()
    device = torch.device("npu:0")
    return {
        "t1": torch.tensor([1.0, 2.0], device=device),
        "t2": torch.tensor([3.0], device=device),
        "t3": torch.tensor([[4.0]], device=device),
    }


def _assert_all_tensors_on_npu(obj):
    if isinstance(obj, torch.Tensor):
        assert obj.device.type == "npu"
        return
    if isinstance(obj, dict):
        for value in obj.values():
            _assert_all_tensors_on_npu(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _assert_all_tensors_on_npu(value)


def _assert_leafs_and_rebuilt_spec(tree, is_leaf=None):
    leaves, spec = _pytree.tree_flatten(tree, is_leaf=is_leaf)

    assert isinstance(leaves, list)
    assert isinstance(spec, _pytree.TreeSpec)
    _assert_all_tensors_on_npu(leaves)

    rebuilt = spec.unflatten(leaves)
    rebuilt_leaves, rebuilt_spec = _pytree.tree_flatten(rebuilt, is_leaf=is_leaf)

    assert rebuilt_spec == spec
    assert len(rebuilt_leaves) == len(leaves)
    _assert_all_tensors_on_npu(rebuilt_leaves)


@pytest.mark.parametrize(
    "tree_factory, expected_leaf_count",
    [
        (lambda ts: ts["t1"], 1),  # 单个 Tensor
        (lambda ts: {"tensor": ts["t1"], "value": 7}, 2),  # 标量与 NPU Tensor 共存
        (lambda ts: [ts["t1"], ts["t2"]], 2),  # list of tensors
        (lambda ts: (ts["t1"], ts["t2"]), 2),  # tuple of tensors
        (lambda ts: {"a": ts["t1"], "b": ts["t2"]}, 2),  # dict
        (lambda ts: {"left": [ts["t1"], (ts["t2"], {"x": ts["t3"]})], "right": ()}, 3),  # nested
        (lambda ts: {"tensor": ts["t1"], "empty": []}, 1),  # 包含 empty list
        (lambda ts: {"tensor": ts["t1"], "empty": ()}, 1),  # 包含 empty tuple
        (lambda ts: {"tensor": ts["t1"], "empty": {}}, 1),  # 包含 empty dict
        (lambda ts: {"tensor": ts["t1"], "value": None}, 2),  # None 与 NPU Tensor 共存
        (lambda ts: {"a": [ts["t1"], None], "b": (3, "x", ts["t2"]), "c": {"d": ts["t3"]}}, 6),  # mixed
    ],
)
def test_tree_flatten_normal_cases_on_npu(npu_tensors, tree_factory, expected_leaf_count):
    """验证常见 pytree 输入在 NPU 上 flatten 的返回结构、叶子列表与 TreeSpec 重建能力。"""
    _require_npu()

    pytree = tree_factory(npu_tensors)
    leaves, spec = _pytree.tree_flatten(pytree)

    assert isinstance(leaves, list)
    assert isinstance(spec, _pytree.TreeSpec)
    assert len(leaves) == expected_leaf_count
    assert spec.num_leaves == expected_leaf_count
    _assert_all_tensors_on_npu(leaves)

    rebuilt = spec.unflatten(leaves)
    rebuilt_leaves, rebuilt_spec = _pytree.tree_flatten(rebuilt)

    assert isinstance(rebuilt_spec, _pytree.TreeSpec)
    assert rebuilt_spec == spec
    assert len(rebuilt_leaves) == len(leaves)
    _assert_all_tensors_on_npu(rebuilt_leaves)


@pytest.mark.parametrize(
    "is_leaf, expected_leaf_count, expect_nested_leaf",
    [
        (None, 3, False),  # 显式传入 None
        (lambda obj: isinstance(obj, tuple), 2, True),  # 非 None Callable
    ],
)
def test_tree_flatten_is_leaf_variants_on_npu(
    npu_tensors, is_leaf, expected_leaf_count, expect_nested_leaf
):
    """验证 is_leaf 参数传入 None/Callable 时的 flatten 行为。"""
    _require_npu()

    pytree = {"x": npu_tensors["t1"], "y": (npu_tensors["t2"], 3)}
    leaves, spec = _pytree.tree_flatten(pytree, is_leaf=is_leaf)

    assert isinstance(leaves, list)
    assert isinstance(spec, _pytree.TreeSpec)
    assert len(leaves) == expected_leaf_count
    assert spec.num_leaves == expected_leaf_count

    if expect_nested_leaf:
        assert isinstance(leaves[1], tuple)
        _assert_all_tensors_on_npu(leaves[1])
    else:
        _assert_all_tensors_on_npu(leaves)

    rebuilt = spec.unflatten(leaves)
    rebuilt_leaves, rebuilt_spec = _pytree.tree_flatten(rebuilt, is_leaf=is_leaf)
    assert rebuilt_spec == spec
    assert len(rebuilt_leaves) == len(leaves)

    if expect_nested_leaf:
        assert isinstance(rebuilt_leaves[1], tuple)
        _assert_all_tensors_on_npu(rebuilt_leaves[1])
    else:
        _assert_all_tensors_on_npu(rebuilt_leaves)


def test_tree_flatten_tree_spec_for_npu_tensor_can_reconstruct(npu_tensors):
    """验证包含 NPU Tensor 的结构可被 TreeSpec 正确重建。"""
    _require_npu()

    pytree = {
        "outer": [npu_tensors["t1"], (npu_tensors["t2"], {"inner": npu_tensors["t3"]})],
        "empty": (),
    }

    _assert_leafs_and_rebuilt_spec(pytree)


def test_tree_flatten_invalid_is_leaf_type_raises():
    """验证非 Callable 的 is_leaf 会触发 TypeError。"""
    _require_npu()

    with pytest.raises(TypeError):
        _pytree.tree_flatten(torch.tensor([1.0], device=torch.device("npu:0")), is_leaf=123)


def test_tree_flatten_cyclic_structure_raises():
    """验证循环引用 pytree 会抛出递归异常。"""
    _require_npu()

    cyclic = [torch.tensor([1.0], device=torch.device("npu:0"))]
    cyclic.append(cyclic)

    with pytest.raises(RecursionError):
        _pytree.tree_flatten(cyclic)
