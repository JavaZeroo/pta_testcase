"""
测试目的：
1. 验证 torch.nn.Module.named_parameters 在 NPU 环境中可正常遍历参数，返回 (name, Parameter) 元组，且参数位于 NPU。
2. 覆盖 prefix、recurse、remove_duplicate 的默认/显式传参、None/非None、主要类型、正常/异常、边界场景。
3. 验证无参数模块、单层模块、嵌套模块、共享参数模块在 NPU 上的命名参数遍历行为。

API 名称：torch.nn.Module.named_parameters

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 默认参数 prefix='' recurse=True remove_duplicate=True | 已覆盖 | 通过无参调用验证默认行为 |
| 显式传入 prefix='' recurse=True remove_duplicate=True | 已覆盖 | 验证参数“传入”时与默认行为一致 |
| prefix="" | 已覆盖 | 空字符串边界值 |
| prefix="custom" | 已覆盖 | 非空字符串前缀拼接到参数名 |
| prefix=None | 已覆盖 | 非法类型通过 pytest.raises 验证 TypeError |
| recurse=True | 已覆盖 | 显式递归遍历所有子模块 |
| recurse=False | 已覆盖 | 仅遍历当前模块直系参数 |
| recurse=None | 已覆盖 | None 作为假值时与 False 行为一致 |
| remove_duplicate=True | 已覆盖 | 共享参数去重 |
| remove_duplicate=False | 已覆盖 | 共享参数不去重 |
| remove_duplicate=None | 已覆盖 | None 作为假值时与 False 行为一致 |
| module 无参数 | 已覆盖 | ReLU 模块返回空迭代器 |
| module 有参数（Linear） | 已覆盖 | 验证标准参数名 weight/bias 与 NPU 设备 |
| 嵌套模块 | 已覆盖 | Sequential/子模块层级参数名展开 |
| 共享参数 | 已覆盖 | 同一 Parameter 被两个属性引用时的去重/重复返回 |
| 异常传参 | 已覆盖 | prefix 非 str 时通过 pytest.raises 验证 TypeError |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 参数数值正确性 | 本用例聚焦接口返回结构、名称与设备，不校验具体数值 |
| 多卡/分布式 NPU 场景 | 当前仅验证单卡 NPU 上的基础功能 |
| 其他所有非法参数组合 | 已覆盖主要异常路径和边界值，未逐一穷举所有非法输入 |
"""

import pytest

import torch
import torch.nn as nn
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Module.named_parameters 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Module.named_parameters 测试。")


def _assert_named_parameter_items(items, expected_names):
    assert len(items) == len(expected_names)
    for (name, param), expected_name in zip(items, expected_names):
        assert isinstance(name, str)
        assert isinstance(param, torch.nn.Parameter)
        assert name == expected_name
        assert param.device.type == "npu"


class NestedSharedModule(nn.Module):
    def __init__(self):
        super().__init__()
        # 共享参数：两个属性指向同一个 Parameter 对象
        shared = nn.Parameter(torch.ones(2, 2))
        self.shared = shared
        self.shared_alias = shared
        # 嵌套模块：包含可训练参数
        self.block = nn.Sequential(nn.Linear(2, 2), nn.ReLU())


@pytest.fixture()
def npu_device():
    _require_npu()
    device = torch.device("npu:0")
    probe = torch.tensor([1], device=device)
    assert probe.device.type == "npu"
    return device


@pytest.fixture()
def linear_module_npu(npu_device):
    module = nn.Linear(2, 3)
    module = module.to(npu_device)
    return module


@pytest.fixture()
def empty_module_npu(npu_device):
    module = nn.ReLU()
    module = module.to(npu_device)
    return module


@pytest.fixture()
def nested_shared_module_npu(npu_device):
    module = NestedSharedModule()
    module = module.to(npu_device)
    return module


def test_named_parameters_default_args_on_linear(linear_module_npu):
    """验证默认参数下，Linear 模块可正确返回 (name, Parameter) 元组并位于 NPU。"""
    items = list(linear_module_npu.named_parameters())

    _assert_named_parameter_items(items, ["weight", "bias"])


def test_named_parameters_explicit_default_args_on_linear(linear_module_npu):
    """验证显式传入默认参数时，Linear 模块遍历结果与默认调用一致。"""
    items = list(linear_module_npu.named_parameters(prefix="", recurse=True, remove_duplicate=True))

    _assert_named_parameter_items(items, ["weight", "bias"])


def test_named_parameters_empty_module_returns_empty_iterator(empty_module_npu):
    """验证无参数模块在 NPU 上返回空迭代器。"""
    items = list(empty_module_npu.named_parameters())

    assert items == []


def test_named_parameters_prefix_custom_on_nested_module(nested_shared_module_npu):
    """验证 prefix='custom' 时，嵌套模块参数名会被正确拼接。"""
    items = list(nested_shared_module_npu.named_parameters(prefix="custom"))

    _assert_named_parameter_items(
        items,
        ["custom.shared", "custom.block.0.weight", "custom.block.0.bias"],
    )


def test_named_parameters_recurse_false_only_direct_parameters(nested_shared_module_npu):
    """验证 recurse=False 时仅遍历当前模块直系参数，并保持 NPU 设备属性。"""
    items = list(nested_shared_module_npu.named_parameters(recurse=False))

    _assert_named_parameter_items(items, ["shared"])


def test_named_parameters_recurse_true_on_nested_module(nested_shared_module_npu):
    """验证 recurse=True 时会递归遍历嵌套子模块参数。"""
    items = list(nested_shared_module_npu.named_parameters(recurse=True))

    _assert_named_parameter_items(items, ["shared", "block.0.weight", "block.0.bias"])


def test_named_parameters_recurse_none_behaves_like_false(nested_shared_module_npu):
    """验证 recurse=None 作为假值时，行为与 recurse=False 一致。"""
    items = list(nested_shared_module_npu.named_parameters(recurse=None))

    _assert_named_parameter_items(items, ["shared"])


def test_named_parameters_remove_duplicate_true_deduplicates_shared_parameter(nested_shared_module_npu):
    """验证 remove_duplicate=True 时，共享参数仅返回一次。"""
    items = list(nested_shared_module_npu.named_parameters(remove_duplicate=True))

    _assert_named_parameter_items(items, ["shared", "block.0.weight", "block.0.bias"])
    assert "shared_alias" not in [name for name, _ in items]


def test_named_parameters_remove_duplicate_false_keeps_shared_aliases(nested_shared_module_npu):
    """验证 remove_duplicate=False 时，同一共享参数会以多个名字返回。"""
    items = list(nested_shared_module_npu.named_parameters(remove_duplicate=False))

    _assert_named_parameter_items(
        items,
        ["shared", "shared_alias", "block.0.weight", "block.0.bias"],
    )


def test_named_parameters_remove_duplicate_none_keeps_shared_aliases(nested_shared_module_npu):
    """验证 remove_duplicate=None 作为假值时，行为与 remove_duplicate=False 一致。"""
    items = list(nested_shared_module_npu.named_parameters(remove_duplicate=None))

    _assert_named_parameter_items(
        items,
        ["shared", "shared_alias", "block.0.weight", "block.0.bias"],
    )


@pytest.mark.parametrize("bad_prefix", [None, 1])
def test_named_parameters_invalid_prefix_type_raises(linear_module_npu, bad_prefix):
    """验证 prefix 非字符串时会抛出 TypeError。"""
    with pytest.raises(TypeError):
        list(linear_module_npu.named_parameters(prefix=bad_prefix))
