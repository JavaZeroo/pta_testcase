"""
测试 torch._dynamo.compiled_autograd.compiled_autograd_enabled：
1. 基础常量检查：验证属性存在、类型为 bool、默认值为 False。
2. 依赖 compiled_autograd._enable 的行为检查：仅验证该常量在上下文内切换为 True，
   并在退出或异常退出后恢复。
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _get_compiled_autograd():
    assert hasattr(torch, "_dynamo"), "缺少 torch._dynamo。"
    assert hasattr(torch._dynamo, "compiled_autograd"), "缺少 torch._dynamo.compiled_autograd。"
    return torch._dynamo.compiled_autograd


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上测试 compiled_autograd_enabled。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上测试 compiled_autograd_enabled。")


def _npu_device():
    return torch.device(f"npu:{torch.npu.current_device()}")


def _make_npu_tensor(*, requires_grad=False):
    return torch.randn(4, device=_npu_device(), requires_grad=requires_grad)


def _dummy_compiler_fn(graph_module):
    """返回 GraphModule.forward，用于触发 compiled autograd 的正常路径。"""
    return graph_module.forward


def test_compiled_autograd_enabled_interface_and_default():
    compiled_autograd = _get_compiled_autograd()

    assert hasattr(compiled_autograd, "compiled_autograd_enabled")
    assert isinstance(compiled_autograd.compiled_autograd_enabled, bool)
    assert compiled_autograd.compiled_autograd_enabled is False
    assert not callable(compiled_autograd.compiled_autograd_enabled)


def test_compiled_autograd_enabled_enable_enter_exit():
    _require_npu()
    compiled_autograd = _get_compiled_autograd()

    assert hasattr(compiled_autograd, "compiled_autograd_enabled")
    assert hasattr(compiled_autograd, "_enable")
    assert callable(compiled_autograd._enable)

    x = _make_npu_tensor(requires_grad=True)
    with compiled_autograd._enable(_dummy_compiler_fn):
        assert compiled_autograd.compiled_autograd_enabled is True
        y = (x * 2).sum()
        y.backward()
        assert x.grad is not None
        assert isinstance(x.grad, torch.Tensor)
        assert x.grad.device.type == "npu"
        assert x.grad.device == x.device

    assert compiled_autograd.compiled_autograd_enabled is False


def test_compiled_autograd_enabled_nested_and_exception_restore():
    _require_npu()
    compiled_autograd = _get_compiled_autograd()

    assert hasattr(compiled_autograd, "compiled_autograd_enabled")
    assert hasattr(compiled_autograd, "_enable")

    x = _make_npu_tensor(requires_grad=True)
    assert compiled_autograd.compiled_autograd_enabled is False

    with compiled_autograd._enable(_dummy_compiler_fn):
        assert compiled_autograd.compiled_autograd_enabled is True

        with pytest.raises(RuntimeError, match="inner failure"):
            with compiled_autograd._enable(_dummy_compiler_fn, dynamic=False):
                assert compiled_autograd.compiled_autograd_enabled is True
                (x * 3).sum().backward()
                raise RuntimeError("inner failure")

        assert compiled_autograd.compiled_autograd_enabled is True

    assert compiled_autograd.compiled_autograd_enabled is False
