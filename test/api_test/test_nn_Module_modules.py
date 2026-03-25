"""
测试目的：
1. 验证 `torch.nn.Module.modules()` 在 NPU 上可正常运行，返回迭代器，并且遍历结果包含自身。
2. 覆盖不同模块结构：空容器、单模块、包含子模块的 `Sequential`、嵌套子模块、共享子模块去重。
3. 验证非法传参时会抛出 `TypeError`，并使用 `pytest.raises` 进行异常断言。

API 名称：torch.nn.Module.modules

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 参数传/不传 | 已覆盖 | 正常用例调用 `modules()` 不传参；异常用例传入位置参数/关键字参数触发 `TypeError` |
| None/非None | 不适用 | 该 API 签名为 `modules()`，无显式参数可传入 None/非 None |
| 主要枚举值 | 不适用 | 该 API 无枚举型参数 |
| 主要类型 | 已覆盖 | 覆盖 `nn.Linear`、`nn.ReLU`、`nn.Sequential`、自定义 `nn.Module`、空 `nn.Sequential()` |
| 正常/异常场景 | 已覆盖 | 正常遍历、共享子模块去重、非法位置参数和关键字参数异常 |
| 边界值 | 已覆盖 | 空 `Sequential()`、单模块、重复引用同一子模块 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 模块内部数值正确性 | `modules()` 仅负责遍历模块树，不涉及前向数值计算 |
| 多 NPU 卡及跨卡迁移策略 | 当前用例聚焦单卡 NPU 上的基础行为，不依赖多卡环境 |
"""

import pytest

import torch
import torch.nn as nn
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Module.modules 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Module.modules 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device("npu:0")


def _build_single_module():
    return nn.Linear(4, 2, bias=False)


def _build_sequential_module():
    return nn.Sequential(
        nn.Linear(4, 3),
        nn.ReLU(),
        nn.Sequential(nn.Linear(3, 2), nn.ReLU()),
    )


def _build_shared_submodule():
    shared_relu = nn.ReLU()

    class SharedNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.branch1 = shared_relu
            self.branch2 = shared_relu

    return SharedNet()


@pytest.mark.parametrize(
    "module_factory, expected_count",
    [
        (_build_single_module, 1),
        (_build_sequential_module, 6),
        (_build_shared_submodule, 2),
    ],
)
def test_module_modules_normal_cases(npu_device, module_factory, expected_count):
    """验证不同模块结构下的遍历、包含自身、计数与类型行为。"""
    module = module_factory().to(npu_device)

    modules_iter = module.modules()
    assert iter(modules_iter) is modules_iter

    modules_list = list(modules_iter)
    assert modules_list
    assert modules_list[0] is module
    assert len(modules_list) == expected_count
    assert all(isinstance(item, nn.Module) for item in modules_list)
    assert len({id(item) for item in modules_list}) == len(modules_list)


def test_module_modules_empty_sequential_boundary(npu_device):
    """验证空 `Sequential` 作为边界值时仍会返回自身。"""
    module = nn.Sequential().to(npu_device)

    modules_iter = module.modules()
    assert iter(modules_iter) is modules_iter

    modules_list = list(modules_iter)
    assert modules_list == [module]
    assert all(isinstance(item, nn.Module) for item in modules_list)


def test_module_modules_after_to_npu_parameters_on_npu(npu_device):
    """验证模块 `.to("npu")` 后，`modules()` 仍可正常遍历且参数位于 NPU。"""
    module = nn.Sequential(
        nn.Linear(4, 3),
        nn.Sequential(nn.Linear(3, 2)),
    ).to(npu_device)

    modules_list = list(module.modules())

    assert modules_list[0] is module
    assert len(modules_list) == 4
    assert all(isinstance(item, nn.Module) for item in modules_list)

    params = list(module.parameters())
    assert params
    assert all(param.device.type == "npu" for param in params)
    assert all(param.device.index == 0 for param in params)


@pytest.mark.parametrize(
    "kwargs, args",
    [
        ({}, ("unexpected",)),
        ({"recurse": True}, ()),
    ],
)
def test_module_modules_invalid_argument_raises(npu_device, kwargs, args):
    """验证 `modules()` 传入非法位置参数或关键字参数时抛出 `TypeError`。"""
    module = nn.Sequential(nn.Linear(2, 2)).to(npu_device)

    with pytest.raises(TypeError):
        module.modules(*args, **kwargs)
