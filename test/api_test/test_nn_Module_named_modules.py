"""
测试目的：
1. 验证 torch.nn.Module.named_modules 在 NPU 场景下可正常遍历模块树，并返回 (name, module) 元组迭代器。
2. 覆盖 memo / prefix / remove_duplicate 三个参数在“传入/不传”“None/非None”“主要枚举值”“异常输入”等维度上的行为。
3. 验证嵌套模块、共享子模块、预置 memo 等典型结构下的遍历顺序、去重行为与名称层级。
4. 验证模型迁移到 NPU 后，模块参数确实位于 NPU 设备上。

API 名称：torch.nn.Module.named_modules

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| memo | 已覆盖 | 默认不传、显式传入 None、显式传入空 set()、显式传入预置 module set()、非法对象触发异常 |
| prefix | 已覆盖 | 默认不传、显式空字符串、显式非空字符串 "myprefix"、非法 None 触发异常 |
| remove_duplicate | 已覆盖 | 默认 True、显式 True、显式 False |
| 嵌套模块 | 已覆盖 | 多层 Sequential 嵌套 |
| 共享子模块 | 已覆盖 | 同一个子模块被多个路径复用，验证去重与重复遍历 |
| NPU 设备 | 已覆盖 | 模型参数迁移到 npu:0 后继续验证 named_modules 行为 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 循环引用模块图 | 非非常规模块树场景，可能引入遍历风险；当前用例已覆盖常见嵌套与共享子模块 |
| 多卡设备切换 | 当前环境仅按单卡 NPU 场景设计验证，不依赖多卡拓扑 |
| remove_duplicate 非 bool 类型 | 该参数在实现中按 truthy/falsy 处理，非 bool 仍可正常执行，额外覆盖收益有限 |
"""

import pytest

import torch
import torch_npu  # noqa: F401
import torch.nn as nn


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Module.named_modules 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Module.named_modules 测试。")


class _NestedSharedModule(nn.Module):
    def __init__(self):
        super().__init__()
        shared_relu = nn.ReLU()
        self.branch1 = nn.Sequential(nn.Linear(4, 4), shared_relu)
        self.branch2 = nn.Sequential(shared_relu, nn.Linear(4, 2))
        self.head = nn.Sequential(nn.Identity(), nn.Linear(2, 1))


@pytest.fixture()
def npu_model():
    _require_npu()
    model = _NestedSharedModule().to(torch.device("npu:0"))
    for param in model.parameters():
        assert param.device.type == "npu"
        assert param.device.index == 0
    return model


def _collect_named_modules(module, **kwargs):
    return list(module.named_modules(**kwargs))


def _assert_named_modules_result(results, expected_names, expected_modules):
    assert len(results) == len(expected_names)
    for (name, submodule), expected_name, expected_module in zip(
        results, expected_names, expected_modules
    ):
        assert isinstance(name, str)
        assert isinstance(submodule, nn.Module)
        assert name == expected_name
        assert submodule is expected_module


def test_named_modules_default_args_and_nested_shared_remove_duplicate_true(npu_model):
    """验证默认参数下的遍历顺序、名称层级和共享子模块去重行为。"""
    results = _collect_named_modules(npu_model)

    expected_names = [
        "",
        "branch1",
        "branch1.0",
        "branch1.1",
        "branch2",
        "branch2.1",
        "head",
        "head.0",
        "head.1",
    ]
    expected_modules = [
        npu_model,
        npu_model.branch1,
        npu_model.branch1[0],
        npu_model.branch1[1],
        npu_model.branch2,
        npu_model.branch2[1],
        npu_model.head,
        npu_model.head[0],
        npu_model.head[1],
    ]

    _assert_named_modules_result(results, expected_names, expected_modules)
    assert results[3][1] is npu_model.branch2[0]


def test_named_modules_explicit_none_and_empty_memo_matches_default(npu_model):
    """验证 memo 显式传 None、空 set() 时与默认行为一致。"""
    default_results = _collect_named_modules(npu_model)
    none_results = _collect_named_modules(npu_model, memo=None)
    empty_memo_results = _collect_named_modules(npu_model, memo=set())

    assert none_results == default_results
    assert empty_memo_results == default_results


def test_named_modules_with_preseeded_memo_skips_seeded_shared_module(npu_model):
    """验证 memo 预置已有模块时，会跳过已在 memo 中的模块。"""
    seeded_memo = {npu_model.branch1[1]}
    results = _collect_named_modules(npu_model, memo=seeded_memo, remove_duplicate=False)

    expected_names = [
        "",
        "branch1",
        "branch1.0",
        "branch2",
        "branch2.1",
        "head",
        "head.0",
        "head.1",
    ]
    expected_modules = [
        npu_model,
        npu_model.branch1,
        npu_model.branch1[0],
        npu_model.branch2,
        npu_model.branch2[1],
        npu_model.head,
        npu_model.head[0],
        npu_model.head[1],
    ]

    _assert_named_modules_result(results, expected_names, expected_modules)


def test_named_modules_with_prefix_myprefix(npu_model):
    """验证 prefix 参数会正确拼接模块层级名称。"""
    results = _collect_named_modules(npu_model, prefix="myprefix")

    expected_names = [
        "myprefix",
        "myprefix.branch1",
        "myprefix.branch1.0",
        "myprefix.branch1.1",
        "myprefix.branch2",
        "myprefix.branch2.1",
        "myprefix.head",
        "myprefix.head.0",
        "myprefix.head.1",
    ]
    expected_modules = [
        npu_model,
        npu_model.branch1,
        npu_model.branch1[0],
        npu_model.branch1[1],
        npu_model.branch2,
        npu_model.branch2[1],
        npu_model.head,
        npu_model.head[0],
        npu_model.head[1],
    ]

    _assert_named_modules_result(results, expected_names, expected_modules)


def test_named_modules_with_explicit_default_args(npu_model):
    """验证显式传入默认参数与不传参行为一致。"""
    default_results = _collect_named_modules(npu_model)
    explicit_results = _collect_named_modules(
        npu_model, memo=None, prefix="", remove_duplicate=True
    )

    assert explicit_results == default_results


def test_named_modules_remove_duplicate_false_exposes_shared_submodule_twice(npu_model):
    """验证 remove_duplicate=False 时共享子模块会被重复遍历。"""
    results = _collect_named_modules(npu_model, remove_duplicate=False)

    expected_names = [
        "",
        "branch1",
        "branch1.0",
        "branch1.1",
        "branch2",
        "branch2.0",
        "branch2.1",
        "head",
        "head.0",
        "head.1",
    ]
    expected_modules = [
        npu_model,
        npu_model.branch1,
        npu_model.branch1[0],
        npu_model.branch1[1],
        npu_model.branch2,
        npu_model.branch2[0],
        npu_model.branch2[1],
        npu_model.head,
        npu_model.head[0],
        npu_model.head[1],
    ]

    _assert_named_modules_result(results, expected_names, expected_modules)
    assert results[3][1] is results[5][1]


def test_named_modules_invalid_memo_raises_type_error(npu_model):
    """验证 memo 传入非法对象时通过 pytest.raises 抛出异常。"""
    with pytest.raises(TypeError):
        _collect_named_modules(npu_model, memo=object())


def test_named_modules_invalid_prefix_raises_type_error(npu_model):
    """验证 prefix 传入非法类型时通过 pytest.raises 抛出异常。"""
    with pytest.raises(TypeError):
        _collect_named_modules(npu_model, prefix=None)
