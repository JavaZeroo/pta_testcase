"""
测试目的：
1. 验证 torch.utils._pytree.tree_map 在 NPU 环境下可正确遍历 pytree，并保持输出结构与输入一致。
2. 验证单树、多树 rest、prefix rest、is_leaf、自定义 func、None/非None 叶子以及异常场景的行为。
3. 验证映射过程中的 Tensor 叶子始终位于 NPU 上，且异常可通过 pytest.raises 捕获。

API 名称：torch.utils._pytree.tree_map

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| func | 已覆盖 | identity / type-changing / spy / 非可调用异常 |
| tree | 已覆盖 | list / tuple / dict / nested / None 混合 |
| rests | 已覆盖 | 不传 / 同结构多树 / prefix 结构 / 结构不匹配异常 |
| is_leaf | 已覆盖 | 不传 / 传入自定义谓词，验证 subtree 作为整体叶子 |
| leaf 类型 | 已覆盖 | NPU Tensor / None / Tensor+None 混合 |
| 输出结构 | 已覆盖 | 与输入 pytree 结构一致，或在 is_leaf 下按自定义叶子规则一致 |
| 设备属性 | 已覆盖 | 输出中的 Tensor 叶子仍保持 NPU 设备属性 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 数值结果正确性 | tree_map 主要负责递归映射与结构保持，本测试聚焦调用、结构和设备行为，不做具体数值校验 |
| 大规模 / 超深层 pytree 性能 | 功能测试以基本语义正确性为主，未额外覆盖性能边界 |
| 自定义注册 pytree 类型 | 当前测试聚焦 torch 内置常见 pytree 结构与 NPU Tensor 场景，未引入额外自定义类型注册成本 |
"""

import pytest

import torch
import torch_npu  # noqa: F401

from torch.utils._pytree import tree_leaves, tree_map, tree_structure


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法执行 torch.utils._pytree.tree_map 的 NPU 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法执行 torch.utils._pytree.tree_map 的 NPU 测试。")
    return torch.device("npu:0")


def _make_tensor(device, value):
    return torch.tensor([value], device=device)


def _make_tree(case_name, device):
    if case_name == "list":
        return [_make_tensor(device, 1), _make_tensor(device, 2)]
    if case_name == "tuple":
        return (
            _make_tensor(device, 3),
            (_make_tensor(device, 4), _make_tensor(device, 5)),
        )
    if case_name == "dict":
        return {
            "a": _make_tensor(device, 6),
            "b": _make_tensor(device, 7),
        }
    if case_name == "nested":
        return {
            "x": [_make_tensor(device, 8), (_make_tensor(device, 9), {"y": _make_tensor(device, 10)})],
            "z": _make_tensor(device, 11),
        }
    raise ValueError(f"未知 case: {case_name}")


def _make_rest_trees(device):
    tree1 = {
        "a": [_make_tensor(device, 1), _make_tensor(device, 2)],
        "b": (_make_tensor(device, 3), {"c": _make_tensor(device, 4)}),
    }
    tree2 = {
        "a": [_make_tensor(device, 5), _make_tensor(device, 6)],
        "b": (_make_tensor(device, 7), {"c": _make_tensor(device, 8)}),
    }
    return tree1, tree2


def _assert_all_tensor_leaves_are_npu(tree):
    for leaf in tree_leaves(tree):
        if isinstance(leaf, torch.Tensor):
            assert leaf.device.type == "npu"


@pytest.mark.parametrize("case_name", ["list", "tuple", "dict", "nested"])
def test_tree_map_single_tree_identity_and_structure(case_name):
    """
    验证单树场景下：
    1. tree_map 可正常调用；
    2. func 会对每个叶子执行；
    3. 输出结构与输入一致；
    4. NPU Tensor 叶子仍保持在 NPU 上。
    """
    device = _require_npu()
    tree = _make_tree(case_name, device)

    assert callable(tree_map)

    call_count = 0

    def identity_func(leaf):
        nonlocal call_count
        call_count += 1
        assert isinstance(leaf, torch.Tensor)
        assert leaf.device.type == "npu"
        return leaf

    assert callable(identity_func)
    out = tree_map(identity_func, tree)

    assert tree_structure(out) == tree_structure(tree)
    assert call_count == len(tree_leaves(tree))
    _assert_all_tensor_leaves_are_npu(out)


def test_tree_map_with_rest_trees_and_corresponding_leaves():
    """
    验证 rest 同结构多树场景下：
    1. func 能收到对应位置的多个叶子；
    2. 输出结构与输入一致；
    3. 输出仍保持 NPU Tensor 叶子。
    """
    device = _require_npu()
    tree1, tree2 = _make_rest_trees(device)

    records = []

    def spy_func(left, right):
        records.append((left.device.type, right.device.type, left.shape, right.shape))
        assert isinstance(left, torch.Tensor)
        assert isinstance(right, torch.Tensor)
        assert left.device.type == "npu"
        assert right.device.type == "npu"
        return left

    out = tree_map(spy_func, tree1, tree2)

    assert tree_structure(out) == tree_structure(tree1)
    assert len(records) == len(tree_leaves(tree1))
    for left_device, right_device, left_shape, right_shape in records:
        assert left_device == "npu"
        assert right_device == "npu"
        assert left_shape == right_shape
    _assert_all_tensor_leaves_are_npu(out)


def test_tree_map_with_rest_prefix_structure():
    """
    验证 rest 允许以 tree 为前缀的结构场景。
    """
    device = _require_npu()
    tree1 = [_make_tensor(device, 1), _make_tensor(device, 2)]
    tree2 = [
        [_make_tensor(device, 3), _make_tensor(device, 4)],
        [_make_tensor(device, 5), _make_tensor(device, 6)],
    ]

    records = []

    def func(left, right):
        assert isinstance(left, torch.Tensor)
        assert left.device.type == "npu"
        assert isinstance(right, list)
        right_leaves = tree_leaves(right)
        assert len(right_leaves) == 2
        for leaf in right_leaves:
            assert isinstance(leaf, torch.Tensor)
            assert leaf.device.type == "npu"
        records.append((len(right_leaves), tuple(type(item).__name__ for item in right)))
        return left

    out = tree_map(func, tree1, tree2)

    assert tree_structure(out) == tree_structure(tree1)
    assert len(records) == len(tree1)
    for leaf_count, right_types in records:
        assert leaf_count == 2
        assert right_types == ("Tensor", "Tensor")
    _assert_all_tensor_leaves_are_npu(out)


def test_tree_map_type_changing_func_keeps_structure():
    """
    验证类型变换场景：func 将 Tensor 叶子转换为非 pytree 容器类型时，pytree 结构保持不变。
    """
    device = _require_npu()
    tree = {"a": _make_tensor(device, 1), "b": [_make_tensor(device, 2), _make_tensor(device, 3)]}

    def type_changing_func(leaf):
        return f"{leaf.shape[0]}@{leaf.device.type}"

    out = tree_map(type_changing_func, tree)

    assert tree_structure(out) == tree_structure(tree)
    out_leaves = tree_leaves(out)
    assert len(out_leaves) == len(tree_leaves(tree))
    for leaf in out_leaves:
        assert isinstance(leaf, str)
        assert "npu" in leaf


def test_tree_map_none_and_non_none_leaves():
    """
    验证 tree 中同时存在 None 与非 None 叶子时，tree_map 可正确遍历并处理。
    """
    device = _require_npu()
    tree = {
        "a": None,
        "b": [_make_tensor(device, 1), None],
        "c": (_make_tensor(device, 2), {"d": None}),
    }
    seen = {"none": 0, "tensor": 0}

    def func(leaf):
        if leaf is None:
            seen["none"] += 1
            return "NONE"
        assert isinstance(leaf, torch.Tensor)
        assert leaf.device.type == "npu"
        seen["tensor"] += 1
        return leaf

    out = tree_map(func, tree)

    assert tree_structure(out) == tree_structure(tree)
    assert seen["none"] == 3
    assert seen["tensor"] == 2

    out_leaves = tree_leaves(out)
    assert len(out_leaves) == len(tree_leaves(tree))
    assert sum(isinstance(leaf, str) for leaf in out_leaves) == 3
    assert sum(isinstance(leaf, torch.Tensor) for leaf in out_leaves) == 2
    _assert_all_tensor_leaves_are_npu(out)


def test_tree_map_is_leaf_treats_subtree_as_leaf():
    """
    验证 is_leaf 传入自定义谓词后，可将指定 subtree 作为整体叶子处理。
    """
    device = _require_npu()
    tree = {
        "a": [_make_tensor(device, 1), _make_tensor(device, 2)],
        "b": _make_tensor(device, 3),
    }
    calls = []

    def is_leaf(node):
        return isinstance(node, list)

    def func(node):
        calls.append(type(node).__name__)
        if isinstance(node, list):
            assert len(node) == 2
            for leaf in node:
                assert isinstance(leaf, torch.Tensor)
                assert leaf.device.type == "npu"
            return "LIST_LEAF"
        assert isinstance(node, torch.Tensor)
        assert node.device.type == "npu"
        return node

    out = tree_map(func, tree, is_leaf=is_leaf)

    assert tree_structure(out, is_leaf=is_leaf) == tree_structure(tree, is_leaf=is_leaf)
    assert calls == ["list", "Tensor"]
    out_leaves = tree_leaves(out)
    assert len(out_leaves) == 2
    assert any(isinstance(leaf, str) and leaf == "LIST_LEAF" for leaf in out_leaves)
    assert any(isinstance(leaf, torch.Tensor) and leaf.device.type == "npu" for leaf in out_leaves)


def test_tree_map_non_callable_func_raises_type_error():
    """
    验证 func 非可调用对象时抛出 TypeError。
    """
    device = _require_npu()
    tree = _make_tree("list", device)

    with pytest.raises(TypeError):
        tree_map(123, tree)


def test_tree_map_rest_tree_arity_mismatch_raises_value_error():
    """
    验证 rest 树结构不匹配时抛出 ValueError。
    """
    device = _require_npu()
    tree1 = {"a": _make_tensor(device, 1), "b": _make_tensor(device, 2)}
    tree2 = {"a": _make_tensor(device, 3)}

    with pytest.raises(ValueError):
        tree_map(lambda x, y: x, tree1, tree2)
