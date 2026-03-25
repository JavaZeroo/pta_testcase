"""
测试目的：
1. 验证 torch.utils._pytree.tree_unflatten 在 NPU 环境下可正常调用，并可与 tree_flatten 形成结构恢复的正向链路。
2. 覆盖 leaves / treespec 的传参方式、None/非 None、主要输入类型、主要 pytree 容器类型以及异常场景。
3. 验证返回结果中的 Tensor 叶子保持在 NPU 设备上，且仅检查结构，不做具体数值正确性校验。

API 名称：torch.utils._pytree.tree_unflatten

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| leaves | 已覆盖 | list / tuple / generator / 非可迭代对象 / 数量不匹配 / 空 leaves |
| treespec | 已覆盖 | 合法 TreeSpec / None / 非 TreeSpec 类型 / 缺参 |
| 传参方式 | 已覆盖 | 位置参数 / 关键字参数 / 缺参 |
| 容器类型 | 已覆盖 | list / tuple / dict / 嵌套结构 / 空容器 / 单叶 |
| 叶子类型 | 已覆盖 | NPU Tensor |
| 结果设备 | 已覆盖 | 返回结果中的 Tensor 叶子保持 NPU 设备属性 |
| 异常场景 | 已覆盖 | TypeError / ValueError |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 自定义注册 pytree 节点 | 本文件聚焦 tree_unflatten 对内置 pytree 容器的基础行为，不额外引入自定义注册类 |
| 多 NPU 卡及跨设备组合场景 | 当前用例以单卡 NPU 的基础功能验证为主，不依赖多卡环境 |
| 具体数值正确性 | tree_unflatten 的职责是恢复结构，本文仅验证结构与设备属性，不做数值比对 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 tree_unflatten 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 tree_unflatten 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device("npu:0")


@pytest.fixture(scope="module")
def npu_tensor_triplet(npu_device):
    return (
        torch.tensor([1.0, 2.0], device=npu_device),
        torch.tensor([3.0], device=npu_device),
        torch.tensor([4.0, 5.0, 6.0], device=npu_device),
    )


def _assert_tensor_leaves_on_npu(tree):
    leaves, _ = torch.utils._pytree.tree_flatten(tree)
    for leaf in leaves:
        if isinstance(leaf, torch.Tensor):
            assert leaf.device.type == "npu"
            assert leaf.device.index == 0


def _assert_flattened_leaves_match_expected(tree, expected_leaves):
    actual_leaves, _ = torch.utils._pytree.tree_flatten(tree)
    assert len(actual_leaves) == len(expected_leaves)

    for actual, expected in zip(actual_leaves, expected_leaves):
        if isinstance(expected, torch.Tensor):
            assert isinstance(actual, torch.Tensor)
            assert torch.equal(actual, expected)
            assert actual.device == expected.device
        else:
            assert actual == expected


@pytest.mark.parametrize(
    "tree_builder, expected_type",
    [
        (lambda t1, t2, t3: [t1, (t2, {"c": t3})], list),
        (lambda t1, t2, t3: (t1, {"a": [t2, ()]}, []), tuple),
        (lambda t1, t2, t3: {"left": [], "mid": {"inner": (t1, t2)}, "right": t3}, dict),
        (lambda t1, t2, t3: t1, torch.Tensor),
    ],
)
def test_tree_unflatten_round_trip_and_npu_device(
    npu_tensor_triplet, tree_builder, expected_type
):
    """验证合法 pytree 的 round-trip、返回类型与 NPU 设备属性。"""
    t1, t2, t3 = npu_tensor_triplet
    tree = tree_builder(t1, t2, t3)
    leaves, treespec = torch.utils._pytree.tree_flatten(tree)
    rebuilt = torch.utils._pytree.tree_unflatten(leaves, treespec)

    assert isinstance(rebuilt, expected_type)
    assert torch.utils._pytree.tree_flatten(rebuilt)[1] == treespec
    _assert_flattened_leaves_match_expected(rebuilt, leaves)
    _assert_tensor_leaves_on_npu(rebuilt)

    if isinstance(rebuilt, torch.Tensor):
        assert rebuilt.device.type == "npu"
        assert rebuilt.device.index == 0


@pytest.mark.parametrize(
    "leaves_wrapper",
    [
        list,
        tuple,
        lambda xs: (item for item in xs),
    ],
)
def test_tree_unflatten_accepts_multiple_iterable_leaf_types(
    npu_tensor_triplet, leaves_wrapper
):
    """验证 leaves 既可以是 list/tuple，也可以是 generator 等可迭代对象。"""
    t1, t2, t3 = npu_tensor_triplet
    tree = {"empty_list": [], "empty_tuple": (), "empty_dict": {}, "payload": [t1, (t2, t3)]}
    leaves, treespec = torch.utils._pytree.tree_flatten(tree)

    rebuilt = torch.utils._pytree.tree_unflatten(leaves_wrapper(leaves), treespec)

    assert isinstance(rebuilt, dict)
    assert torch.utils._pytree.tree_flatten(rebuilt)[1] == treespec
    _assert_flattened_leaves_match_expected(rebuilt, leaves)
    _assert_tensor_leaves_on_npu(rebuilt)


def test_tree_unflatten_supports_keyword_arguments(npu_tensor_triplet):
    """验证 tree_unflatten 支持关键字方式传入 leaves 与 treespec。"""
    t1, t2, _ = npu_tensor_triplet
    tree = ({"k1": t1}, [t2, ()])
    leaves, treespec = torch.utils._pytree.tree_flatten(tree)

    rebuilt = torch.utils._pytree.tree_unflatten(leaves=leaves, treespec=treespec)

    assert isinstance(rebuilt, tuple)
    assert torch.utils._pytree.tree_flatten(rebuilt)[1] == treespec
    _assert_flattened_leaves_match_expected(rebuilt, leaves)
    _assert_tensor_leaves_on_npu(rebuilt)


def test_tree_unflatten_missing_arguments_raises(npu_tensor_triplet):
    """验证 leaves 或 treespec 缺参时抛出 TypeError。"""
    t1, _, _ = npu_tensor_triplet

    with pytest.raises(TypeError):
        torch.utils._pytree.tree_unflatten()

    with pytest.raises(TypeError):
        torch.utils._pytree.tree_unflatten([t1])


def test_tree_unflatten_wrong_number_of_leaves_raises(npu_tensor_triplet):
    """验证 leaves 数量与 TreeSpec 不匹配时抛出异常。"""
    t1, t2, t3 = npu_tensor_triplet
    tree = [t1, t2]
    leaves, treespec = torch.utils._pytree.tree_flatten(tree)

    with pytest.raises(ValueError):
        torch.utils._pytree.tree_unflatten(leaves[:-1], treespec)

    with pytest.raises(ValueError):
        torch.utils._pytree.tree_unflatten(leaves + [t3], treespec)


@pytest.mark.parametrize("bad_treespec", [None, 0, "bad", object()])
def test_tree_unflatten_invalid_treespec_raises(npu_tensor_triplet, bad_treespec):
    """验证 treespec 为 None 或非 TreeSpec 类型时抛出 TypeError。"""
    t1, _, _ = npu_tensor_triplet

    with pytest.raises(TypeError):
        torch.utils._pytree.tree_unflatten([t1], bad_treespec)


def test_tree_unflatten_non_iterable_leaves_raises(npu_tensor_triplet):
    """验证 leaves 不是可迭代对象时抛出 TypeError。"""
    t1, t2, _ = npu_tensor_triplet
    tree = [t1, t2]
    _, treespec = torch.utils._pytree.tree_flatten(tree)

    with pytest.raises(TypeError):
        torch.utils._pytree.tree_unflatten(123, treespec)


def test_tree_unflatten_supports_empty_leaves():
    """验证仅由空容器组成的 pytree 可由空 leaves 正确恢复。"""
    tree = {"empty_list": [], "empty_tuple": (), "empty_dict": {}}
    leaves, treespec = torch.utils._pytree.tree_flatten(tree)

    rebuilt = torch.utils._pytree.tree_unflatten(leaves, treespec)

    assert leaves == []
    assert rebuilt == tree
    assert torch.utils._pytree.tree_flatten(rebuilt)[0] == []
    assert torch.utils._pytree.tree_flatten(rebuilt)[1] == treespec
