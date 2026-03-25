"""
测试目的：
1. 验证 torch.nn.Module.buffers 在 NPU 场景下可正常调用，返回迭代器，并能正确遍历模块缓冲区。
2. 覆盖 recurse 传参与不传、None/非None、True/False、模块无 buffer / 有 buffer、嵌套子模块、以及 .to("npu") 后缓冲区位于 NPU 的场景。
3. 覆盖异常场景：recurse 入参的非法布尔转换。

API 名称：torch.nn.Module.buffers

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| recurse=True（默认） | 已覆盖 | 直接调用 buffers()，验证默认递归遍历 |
| recurse=True（显式传参） | 已覆盖 | 显式传入 True，验证传参路径 |
| recurse=False | 已覆盖 | 仅遍历当前模块的直接 buffer |
| recurse=None | 已覆盖 | 作为边界/兼容输入，验证行为等同于 False 的直接遍历结果 |
| module 无 buffer | 已覆盖 | 验证空迭代器行为 |
| module 有 buffer（register_buffer） | 已覆盖 | 验证正常返回 Tensor 迭代结果 |
| 嵌套子模块 | 已覆盖 | 验证 recurse=True 时包含子模块 buffer，recurse=False 时不包含 |
| .to("npu") 后 buffer 设备 | 已覆盖 | 验证遍历到的 buffer 均位于 NPU |
| recurse 非法类型 / 非法布尔转换 | 已覆盖 | 使用 __bool__ 抛异常的对象触发 TypeError |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| buffer 数值正确性 | 本测试聚焦接口行为、迭代器与设备属性，不做具体数值校验 |
| 多 NPU 卡切换 | 当前用例仅验证单卡 NPU 的基本行为，不依赖多卡环境 |
| 更复杂的 buffer 类型组合 | 已覆盖基础 Tensor buffer 与嵌套模块场景，足以验证本 API 的核心功能 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


_DEFAULT_RECURSE = object()


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Module.buffers 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Module.buffers 测试。")


class _LeafModule(torch.nn.Module):
    def __init__(self, with_buffer: bool):
        super().__init__()
        if with_buffer:
            self.register_buffer("leaf_buf", torch.tensor([2.0, 3.0]))


class _RootModule(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer("root_buf", torch.tensor([1.0]))
        self.child_with_buffer = _LeafModule(with_buffer=True)
        self.child_without_buffer = _LeafModule(with_buffer=False)


class _BadRecurse:
    def __bool__(self):
        raise TypeError("recurse 参数无法转换为 bool")


def _assert_buffer_sequence_matches(buffers_list, expected_values):
    assert len(buffers_list) == len(expected_values)
    for actual, expected in zip(buffers_list, expected_values):
        assert isinstance(actual, torch.Tensor)
        assert actual.device.type == "npu"
        assert actual.device.index == 0
        torch.testing.assert_close(actual.cpu(), expected)


@pytest.fixture()
def npu_root_module():
    _require_npu()
    module = _RootModule()
    return module.to("npu:0")


@pytest.fixture()
def npu_empty_module():
    _require_npu()
    return torch.nn.Module().to("npu:0")


@pytest.mark.parametrize(
    "recurse",
    [
        pytest.param(_DEFAULT_RECURSE, id="default"),
        pytest.param(True, id="explicit_true"),
    ],
)
def test_module_buffers_recurse_true_includes_root_and_nested_buffers(npu_root_module, recurse):
    """验证默认/显式 recurse=True 时均返回当前模块与子模块的具体 buffer。"""
    if recurse is _DEFAULT_RECURSE:
        buffers_iter = npu_root_module.buffers()
    else:
        buffers_iter = npu_root_module.buffers(recurse=recurse)

    assert iter(buffers_iter) is buffers_iter
    buffers_list = list(buffers_iter)
    _assert_buffer_sequence_matches(
        buffers_list,
        [torch.tensor([1.0]), torch.tensor([2.0, 3.0])],
    )


def test_module_buffers_recurse_false_only_returns_direct_buffer(npu_root_module):
    """验证 recurse=False 时仅返回当前模块的直接 buffer。"""
    buffers_iter = npu_root_module.buffers(recurse=False)

    assert iter(buffers_iter) is buffers_iter
    buffers_list = list(buffers_iter)
    _assert_buffer_sequence_matches(buffers_list, [torch.tensor([1.0])])


def test_module_buffers_recurse_none_behaves_like_false(npu_root_module):
    """验证 recurse=None 作为边界输入时，表现为不递归遍历。"""
    buffers_iter = npu_root_module.buffers(recurse=None)

    assert iter(buffers_iter) is buffers_iter
    buffers_list = list(buffers_iter)
    _assert_buffer_sequence_matches(buffers_list, [torch.tensor([1.0])])


def test_module_buffers_empty_module_returns_empty_iterator(npu_empty_module):
    """验证无 buffer 模块返回空迭代器。"""
    buffers_iter = npu_empty_module.buffers()

    assert iter(buffers_iter) is buffers_iter
    buffers_list = list(buffers_iter)
    assert buffers_list == []


def test_module_buffers_after_to_npu_buffers_are_on_npu():
    """验证模块经 .to(\"npu\") 后，buffers 的具体内容保持不变且位于 NPU。"""
    _require_npu()
    module = _RootModule()
    cpu_buffers = [buffer.clone() for buffer in module.buffers()]
    module = module.to("npu:0")

    buffers_list = list(module.buffers())
    _assert_buffer_sequence_matches(buffers_list, cpu_buffers)


def test_module_buffers_invalid_recurse_type_raises(npu_root_module):
    """验证 recurse 非法布尔转换时通过 pytest.raises 抛出异常。"""
    with pytest.raises(TypeError):
        list(npu_root_module.buffers(recurse=_BadRecurse()))
