"""
测试目的：
1. 验证 torch._dynamo.comptime.comptime.print 在具备可用 NPU 的环境中可导入、可访问、可调用。
2. 验证该 API 在传参/不传参、None/非 None、不同类型输入、边界输入以及 torch.compile 编译区域中的基本行为，并确保 on_npu 用例实际有 NPU Tensor 参与。
3. 验证异常场景仅通过 pytest.raises 断言，不做伪覆盖或过宽 skip。

API 名称：torch._dynamo.comptime.comptime.print

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 模块导入 | 已覆盖 | 验证 torch._dynamo.comptime 可导入 |
| comptime 对象 | 已覆盖 | 验证 module.comptime 存在且非空 |
| print 属性 | 已覆盖 | 验证 comptime.print 存在且可调用 |
| 传参/不传参 | 已覆盖 | 覆盖缺参、额外参数、正常单参调用 |
| None/非 None | 已覆盖 | 覆盖 None、字符串、整数、Tensor 等代表性输入 |
| 主要类型 | 已覆盖 | 覆盖 NoneType、str、int、list、Tensor |
| 边界值 | 已覆盖 | 覆盖空字符串、空 Tensor、标量 Tensor |
| 编译区域 | 已覆盖 | 使用 torch.compile(eager) 验证 NPU Tensor 进入编译路径 |
| 异常场景 | 已覆盖 | 缺参/多参触发 TypeError |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| stdout 的具体文本内容 | 该 API 主要用于编译期调试，本用例只验证可用性与异常路径，不校验打印文本细节 |
| 不同 backend 的全量组合 | 仅选择 backend=\"eager\" 作为基础可用性验证，避免后端差异导致用例不稳定 |
| 多卡/跨卡行为 | 当前测试聚焦单卡 NPU 基本功能，不覆盖分布式场景 |
| TorchDynamo 内部图结构与缓存策略 | 属于框架内部实现细节，不作为 API 功能测试目标 |
"""

from importlib import import_module
from unittest.mock import patch

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch._dynamo.comptime.comptime.print 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch._dynamo.comptime.comptime.print 测试。")


def _get_comptime_module():
    _require_npu()
    try:
        return import_module("torch._dynamo.comptime")
    except (ImportError, ModuleNotFoundError, AttributeError) as exc:
        pytest.skip(f"当前环境无法导入 torch._dynamo.comptime，跳过测试：{exc}")


def _make_npu_tensor(data, *, empty=False):
    _require_npu()
    if empty:
        return torch.empty(0, device=torch.device("npu:0"))
    return torch.tensor(data, device=torch.device("npu:0"))


def _assert_print_called_with(mock_print, index, expected):
    call_args = mock_print.call_args_list[index].args
    assert len(call_args) == 1
    actual = call_args[0]
    if isinstance(expected, torch.Tensor):
        assert actual is expected
        assert actual.device.type == "npu"
    else:
        assert actual == expected


def _is_known_npu_compile_unsupported(exc):
    msg = str(exc).lower()
    if isinstance(exc, NotImplementedError):
        return True
    return "npu" in msg and any(
        marker in msg
        for marker in (
            "not support",
            "not supported",
            "unsupported",
            "not implement",
            "not implemented",
        )
    )


@pytest.fixture()
def npu_tensor():
    return _make_npu_tensor([1.0, 2.0])


@pytest.fixture()
def comptime_print():
    return _get_comptime_module().comptime.print


def test_torch_dynamo_comptime_import_and_print_attribute_accessible_on_npu(npu_tensor, comptime_print):
    """验证模块导入、comptime 对象与 print 属性可访问。"""
    comptime_mod = _get_comptime_module()

    assert npu_tensor.device.type == "npu"
    assert comptime_mod.__name__ == "torch._dynamo.comptime"
    assert hasattr(comptime_mod, "comptime")

    comptime_obj = comptime_mod.comptime
    assert comptime_obj is not None
    assert hasattr(comptime_obj, "print")
    assert callable(comptime_print)


@pytest.mark.parametrize(
    "value_builder, value_desc",
    [
        (lambda: None, "None"),
        (lambda: "", "空字符串"),
        (lambda: "npu-comptime", "非空字符串"),
        (lambda: 0, "整数零"),
        (lambda: [], "空列表"),
        (lambda: _make_npu_tensor([], empty=True), "空 NPU Tensor"),
        (lambda: _make_npu_tensor([3.0]), "非空 NPU Tensor"),
        (lambda: _make_npu_tensor(3.0), "标量 NPU Tensor"),
    ],
)
def test_torch_dynamo_comptime_print_normal_values_on_npu(comptime_print, npu_tensor, value_builder, value_desc):
    """验证 comptime.print 对代表性 None/非 None、类型与边界值输入的正常调用。"""
    value = value_builder()

    with patch("builtins.print") as mock_print:
        npu_result = comptime_print(npu_tensor)
        result = comptime_print(value)

    assert npu_result is None, "预期 NPU Tensor 参与时 direct-call 返回 None"
    assert result is None, value_desc
    assert mock_print.call_count == 2, value_desc
    _assert_print_called_with(mock_print, 0, npu_tensor)
    _assert_print_called_with(mock_print, 1, value)


def test_torch_dynamo_comptime_print_argument_validation_on_npu(comptime_print, npu_tensor):
    """验证 comptime.print 缺参与多参场景抛出 TypeError。"""
    with pytest.raises(TypeError):
        comptime_print()

    with pytest.raises(TypeError):
        comptime_print(npu_tensor, npu_tensor)


def test_torch_dynamo_comptime_print_inside_torch_compile_on_npu(npu_tensor, comptime_print):
    """验证 comptime.print 在 torch.compile 编译区域内可执行。"""
    comptime_mod = _get_comptime_module()

    if not hasattr(torch, "compile"):
        pytest.skip("当前环境未提供 torch.compile，无法验证 comptime.print 的编译区域行为。")

    def _fn(x):
        comptime_mod.comptime.print(None)
        comptime_mod.comptime.print("compile-path")
        comptime_mod.comptime.print(x)
        comptime_mod.comptime.print(x[:0])
        return x

    try:
        compiled_fn = torch.compile(_fn, backend="eager")
        out = compiled_fn(npu_tensor)
    except (RuntimeError, NotImplementedError) as exc:
        if _is_known_npu_compile_unsupported(exc):
            pytest.skip(f"当前 NPU 后端不支持 torch.compile eager 路径，无法验证 comptime.print：{exc}")
        raise

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == npu_tensor.shape
    assert out.dtype == npu_tensor.dtype
    assert torch.equal(out.cpu(), npu_tensor.cpu())
    assert callable(comptime_print)
