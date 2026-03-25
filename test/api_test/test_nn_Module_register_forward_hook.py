"""
测试目的：
1. 验证 torch.nn.Module.register_forward_hook 在 NPU 场景下可正常注册 forward hook，返回 RemovableHandle，并在前向执行后触发。
2. 覆盖 hook 参数传/不传、None/非None、主要枚举（prepend/with_kwargs/always_call）、主要类型（普通函数、lambda、非 callable）、正常/异常/边界场景。
3. 所有前向计算均使用 NPU Tensor，确保测试实际运行在 NPU 后端。

API 名称：torch.nn.Module.register_forward_hook

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| hook | 已覆盖 | 普通函数、lambda、None、非 callable 对象 |
| prepend | 已覆盖 | 不传默认值、显式 False、True |
| with_kwargs | 已覆盖 | 不传默认值、显式 False、True |
| always_call | 已覆盖 | 不传默认值、显式 False、True |
| 多个 hook | 已覆盖 | 同一模块注册多个 forward hook，验证调用顺序 |
| handle.remove() | 已覆盖 | 注册后移除，验证后续前向不再触发 |
| hook 返回值 | 已覆盖 | 返回 None、返回 NPU Tensor 副本 |
| 异常场景 | 已覆盖 | forward 抛错、注册非 callable hook 抛错 |
| NPU 设备 | 已覆盖 | 模块、输入与 hook 中捕获的 Tensor 均位于 NPU |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值正确性校验 | 本测试聚焦 API 行为、设备属性、触发顺序和异常路径，不做精确数值比对 |
| 多卡 / 分布式 NPU 场景 | 当前用例仅验证单卡 NPU 基本功能，不依赖多卡环境 |
| 更复杂的嵌套模块 hook 级联 | 已覆盖核心 register/remove/触发逻辑，复杂级联属于扩展场景 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Module.register_forward_hook 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Module.register_forward_hook 测试。")


class _NpuForwardHookModule(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer("offset", torch.tensor([1.0, 2.0], device=torch.device("npu:0")))

    def forward(self, x, scale=1.0, bias=None, raise_error=False):
        if raise_error:
            raise RuntimeError("forward 被测试代码显式触发异常")
        out = x * scale + self.offset
        if bias is not None:
            out = out + bias
        return out


class _BadHook:
    pass


@pytest.fixture()
def npu_module_and_input():
    _require_npu()
    module = _NpuForwardHookModule().to(torch.device("npu:0"))
    x = torch.tensor([3.0, 4.0], device=torch.device("npu:0"))
    return module, x


def test_register_forward_hook_function_default_prepend_false_and_remove(npu_module_and_input):
    """验证普通函数 hook 的默认参数、触发情况以及 handle.remove()。"""
    module, x = npu_module_and_input
    call_count = []

    def hook_fn(mod, inputs, output):
        call_count.append((mod, inputs, output))
        return None

    handle = module.register_forward_hook(hook_fn)

    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    out = module(x)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert len(call_count) == 1
    assert call_count[0][0] is module
    assert isinstance(call_count[0][1], tuple)
    assert isinstance(call_count[0][2], torch.Tensor)
    assert call_count[0][2].device.type == "npu"

    handle.remove()
    out2 = module(x)
    assert isinstance(out2, torch.Tensor)
    assert out2.device.type == "npu"
    assert len(call_count) == 1


def test_register_forward_hook_none_hook_raises_type_error_on_call(npu_module_and_input):
    """验证 hook 传入 None 时，前向调用阶段会触发 TypeError。"""
    module, x = npu_module_and_input

    handle = module.register_forward_hook(None)

    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    with pytest.raises(TypeError):
        module(x)

    handle.remove()


def test_register_forward_hook_lambda_prepend_true_orders_before_existing_hooks(npu_module_and_input):
    """验证 lambda hook、prepend=True 以及多个 hook 的调用顺序。"""
    module, x = npu_module_and_input
    call_order = []

    def first_hook(mod, inputs, output):
        call_order.append("first")
        return None

    prepend_hook = lambda mod, inputs, output: call_order.append("prepend") or None  # noqa: E731

    handle_first = module.register_forward_hook(first_hook, prepend=False)
    handle_prepend = module.register_forward_hook(prepend_hook, prepend=True)

    assert isinstance(handle_first, torch.utils.hooks.RemovableHandle)
    assert isinstance(handle_prepend, torch.utils.hooks.RemovableHandle)

    out = module(x)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert call_order == ["prepend", "first"]

    handle_prepend.remove()
    handle_first.remove()


def test_register_forward_hook_prepend_false_explicitly_passed(npu_module_and_input):
    """验证 prepend=False 显式传参时仍可正常注册并触发 hook。"""
    module, x = npu_module_and_input
    call_count = []

    def hook_fn(mod, inputs, output):
        call_count.append("called")
        return None

    handle = module.register_forward_hook(hook_fn, prepend=False)

    assert isinstance(handle, torch.utils.hooks.RemovableHandle)
    out = module(x)
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert call_count == ["called"]

    handle.remove()


def test_register_forward_hook_with_kwargs_true_receives_kwargs(npu_module_and_input):
    """验证 with_kwargs=True 时 hook 可接收到 kwargs，并且输出仍位于 NPU。"""
    module, x = npu_module_and_input
    captured = {}

    def hook_fn(mod, inputs, kwargs, output):
        captured["module"] = mod
        captured["inputs"] = inputs
        captured["kwargs"] = kwargs
        captured["output"] = output
        return None

    handle = module.register_forward_hook(hook_fn, with_kwargs=True)

    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    bias = torch.tensor([0.5, 0.25], device=torch.device("npu:0"))
    out = module(x, scale=2.0, bias=bias)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert captured["module"] is module
    assert isinstance(captured["inputs"], tuple)
    assert isinstance(captured["kwargs"], dict)
    assert "scale" in captured["kwargs"]
    assert "bias" in captured["kwargs"]
    assert isinstance(captured["kwargs"]["bias"], torch.Tensor)
    assert captured["kwargs"]["bias"].device.type == "npu"
    assert isinstance(captured["output"], torch.Tensor)
    assert captured["output"].device.type == "npu"

    handle.remove()


def test_register_forward_hook_with_kwargs_false_receives_positional_inputs(npu_module_and_input):
    """验证 with_kwargs=False 时 hook 仅接收 positional inputs。"""
    module, x = npu_module_and_input
    captured = {}

    def hook_fn(mod, inputs, output):
        captured["module"] = mod
        captured["inputs"] = inputs
        captured["output"] = output
        return None

    handle = module.register_forward_hook(hook_fn, with_kwargs=False)

    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    bias = torch.tensor([0.25, 0.75], device=torch.device("npu:0"))
    out = module(x, 1.5, bias=bias)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert captured["module"] is module
    assert isinstance(captured["inputs"], tuple)
    assert len(captured["inputs"]) == 2
    assert isinstance(captured["inputs"][0], torch.Tensor)
    assert captured["inputs"][0].device.type == "npu"
    assert captured["inputs"][1] == 1.5
    assert isinstance(captured["output"], torch.Tensor)
    assert captured["output"].device.type == "npu"

    handle.remove()


def test_register_forward_hook_with_kwargs_default_omitted(npu_module_and_input):
    """验证 with_kwargs 默认不传时的行为与显式 False 一致。"""
    module, x = npu_module_and_input
    captured = {}

    def hook_fn(mod, inputs, output):
        captured["module"] = mod
        captured["inputs"] = inputs
        captured["output"] = output
        return None

    handle = module.register_forward_hook(hook_fn)

    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    out = module(x)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert captured["module"] is module
    assert isinstance(captured["inputs"], tuple)
    assert len(captured["inputs"]) == 1
    assert isinstance(captured["inputs"][0], torch.Tensor)
    assert captured["inputs"][0].device.type == "npu"
    assert isinstance(captured["output"], torch.Tensor)
    assert captured["output"].device.type == "npu"

    handle.remove()


def test_register_forward_hook_always_call_true_runs_on_forward_error(npu_module_and_input):
    """验证 always_call=True 时，即使 forward 抛错，hook 仍会被调用。"""
    module, x = npu_module_and_input
    captured_outputs = []

    def hook_fn(mod, inputs, output):
        captured_outputs.append(output)
        return None

    handle = module.register_forward_hook(hook_fn, always_call=True)
    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    with pytest.raises(RuntimeError):
        module(x, raise_error=True)

    assert len(captured_outputs) == 1
    assert captured_outputs[0] is None

    handle.remove()


def test_register_forward_hook_always_call_default_omitted_does_not_run_on_forward_error(npu_module_and_input):
    """验证 always_call 默认不传时，forward 发生异常后 hook 不会被调用。"""
    module, x = npu_module_and_input
    call_count = []

    def hook_fn(mod, inputs, output):
        call_count.append((mod, inputs, output))
        return None

    handle = module.register_forward_hook(hook_fn)
    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    with pytest.raises(RuntimeError):
        module(x, raise_error=True)

    assert call_count == []

    handle.remove()


def test_register_forward_hook_always_call_false_does_not_run_on_forward_error(npu_module_and_input):
    """验证 always_call=False 时，forward 发生异常后 hook 不会被调用。"""
    module, x = npu_module_and_input
    call_count = []

    def hook_fn(mod, inputs, output):
        call_count.append((mod, inputs, output))
        return None

    handle = module.register_forward_hook(hook_fn, always_call=False)
    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    with pytest.raises(RuntimeError):
        module(x, raise_error=True)

    assert call_count == []

    handle.remove()


def test_register_forward_hook_modify_output_returns_tensor_on_npu(npu_module_and_input):
    """验证 hook 可通过返回值修改输出，且返回结果仍为 NPU Tensor。"""
    module, x = npu_module_and_input
    captured = {}

    def hook(mod, inputs, output):
        captured["called"] = True
        captured["output"] = output
        return output.clone()

    handle = module.register_forward_hook(hook)

    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    out = module(x)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert captured["called"] is True
    assert isinstance(captured["output"], torch.Tensor)
    assert captured["output"].device.type == "npu"
    assert out.shape == captured["output"].shape
    assert out.data_ptr() != captured["output"].data_ptr()

    handle.remove()


def test_register_forward_hook_non_callable_raises_type_error(npu_module_and_input):
    """验证非 callable hook 在前向触发 hook 时抛出 TypeError。"""
    module, x = npu_module_and_input
    bad_hook = _BadHook()

    handle = module.register_forward_hook(bad_hook)

    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    with pytest.raises(TypeError):
        module(x)

    handle.remove()
