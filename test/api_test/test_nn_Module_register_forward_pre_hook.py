"""
测试目的：
1. 验证 torch.nn.Module.register_forward_pre_hook 在 NPU 场景下可正常注册、触发与移除。
2. 覆盖 hook 类型、prepend、with_kwargs、hook 返回 None/非 None、多个 hook 协作、异常场景等核心行为。
3. 验证模型与输入均位于 NPU，且 hook 的触发顺序、输入修改、handle.remove() 行为符合预期。

API 名称：torch.nn.Module.register_forward_pre_hook

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| hook 类型 | 已覆盖 | 普通函数 / lambda / 绑定成员方法 |
| prepend | 已覆盖 | False / True，验证 hook 注册与触发顺序 |
| with_kwargs | 已覆盖 | False / True，验证仅 args 与 args+kwargs 两条路径 |
| hook 返回值 | 已覆盖 | 返回 None / 返回修改后的单值输入 / 返回修改后的 tuple 输入 |
| 多个 hook | 已覆盖 | 同一模块注册多个 pre-hook，并验证触发顺序 |
| handle.remove() | 已覆盖 | 移除指定 handle 后不再触发对应 hook |
| 异常场景 | 已覆盖 | 非 callable 注册、hook 主动抛出异常 |
| NPU 设备 | 已覆盖 | 模型、输入、hook 触发过程均在 NPU |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值正确性 | 本测试聚焦接口触发、输入传递与设备行为，不做具体数值精确比对 |
| 多卡 / 分布式 NPU 场景 | 当前仅验证单卡 NPU 的基本功能路径，不依赖多卡环境 |
| 更复杂的嵌套输入结构 | 本 API 的核心行为已通过单输入与 kwargs 场景覆盖，足以验证接口功能 |
"""

import pytest

import torch
import torch_npu  # noqa: F401
from torch.utils.hooks import RemovableHandle


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Module.register_forward_pre_hook 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Module.register_forward_pre_hook 测试。")


class _PreHookModule(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer("anchor", torch.ones(1))
        self.events = []

    def forward(self, x, repeat=1):
        self.events.append(("forward", tuple(x.shape), x.device.type, repeat))
        return x.repeat(repeat, 1)


class _BoundMethodHookRecorder:
    def __init__(self):
        self.events = []

    def pre_hook(self, module, args, kwargs):
        self.events.append(("bound_method", tuple(args[0].shape), kwargs["repeat"], args[0].device.type))
        modified = args[0].reshape(1, -1)
        return (modified,), {**kwargs, "repeat": 3}


@pytest.fixture()
def npu_module():
    _require_npu()
    return _PreHookModule().to(torch.device("npu:0"))


@pytest.fixture()
def npu_input():
    _require_npu()
    return torch.arange(6, dtype=torch.float32, device=torch.device("npu:0")).reshape(2, 3)


def test_module_register_forward_pre_hook_function_default_prepend_and_remove(npu_module, npu_input):
    """验证普通函数 hook、默认 prepend=False、输入修改、handle.remove() 与 NPU 设备行为。"""

    def hook_fn(module, args):
        module.events.append(("hook_fn", tuple(args[0].shape), args[0].device.type))
        modified = args[0].reshape(1, -1)
        return (modified,)

    handle = npu_module.register_forward_pre_hook(hook_fn)

    assert isinstance(handle, RemovableHandle)
    assert npu_module.anchor.device.type == "npu"
    assert npu_input.device.type == "npu"
    assert callable(hook_fn)

    out = npu_module(npu_input, repeat=2)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert tuple(out.shape) == (2, 6)
    assert len(npu_module.events) == 2
    assert npu_module.events[0][0] == "hook_fn"
    assert npu_module.events[1][0] == "forward"
    assert npu_module.events[0][2] == "npu"
    assert npu_module.events[1][2] == "npu"
    assert npu_module.events[1][1] == (1, 6)
    assert npu_module.events[1][3] == 2

    handle.remove()
    npu_module.events.clear()

    out_after_remove = npu_module(npu_input)
    assert isinstance(out_after_remove, torch.Tensor)
    assert out_after_remove.device.type == "npu"
    assert tuple(out_after_remove.shape) == (2, 3)
    assert len(npu_module.events) == 1
    assert npu_module.events[0][0] == "forward"
    assert npu_module.events[0][1] == (2, 3)


def test_module_register_forward_pre_hook_single_value_return_is_wrapped_to_tuple(npu_module, npu_input):
    """验证 hook 返回单个非 tuple 输入值时，框架会自动包装为 args tuple 传给 forward。"""

    def hook_fn(module, args):
        module.events.append(("single_value_hook", tuple(args[0].shape), args[0].device.type))
        return args[0].reshape(1, -1)

    handle = npu_module.register_forward_pre_hook(hook_fn)

    assert isinstance(handle, RemovableHandle)

    out = npu_module(npu_input, repeat=2)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert tuple(out.shape) == (2, 6)
    assert len(npu_module.events) == 2
    assert npu_module.events[0][0] == "single_value_hook"
    assert npu_module.events[0][1] == (2, 3)
    assert npu_module.events[0][2] == "npu"
    assert npu_module.events[1][0] == "forward"
    assert npu_module.events[1][1] == (1, 6)
    assert npu_module.events[1][2] == "npu"
    assert npu_module.events[1][3] == 2

    handle.remove()


def test_module_register_forward_pre_hook_lambda_with_kwargs_prepend_and_multiple_hooks(npu_module, npu_input):
    """验证 lambda hook、with_kwargs=True、prepend=True、多个 hook 与 handle.remove() 协作。"""

    record_hook = lambda module, args, kwargs: (  # noqa: E731
        module.events.append(("record_hook", tuple(args[0].shape), kwargs["repeat"], args[0].device.type))
        or None
    )

    def prepend_hook(module, args, kwargs):
        module.events.append(("prepend_hook", tuple(args[0].shape), kwargs["repeat"], args[0].device.type))
        return args, {**kwargs, "repeat": 2}

    handle_prepend = npu_module.register_forward_pre_hook(prepend_hook, prepend=True, with_kwargs=True)
    handle_record = npu_module.register_forward_pre_hook(record_hook, with_kwargs=True)

    assert isinstance(handle_prepend, RemovableHandle)
    assert isinstance(handle_record, RemovableHandle)
    assert callable(prepend_hook)
    assert callable(record_hook)

    out = npu_module(npu_input, repeat=1)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert tuple(out.shape) == (4, 3)
    assert len(npu_module.events) == 3
    assert npu_module.events[0][0] == "prepend_hook"
    assert npu_module.events[1][0] == "record_hook"
    assert npu_module.events[2][0] == "forward"
    assert npu_module.events[0][1] == (2, 3)
    assert npu_module.events[1][2] == 2
    assert npu_module.events[2][3] == 2
    assert npu_module.events[0][3] == "npu"
    assert npu_module.events[1][3] == "npu"
    assert npu_module.events[2][2] == "npu"

    handle_prepend.remove()
    npu_module.events.clear()

    out_after_remove = npu_module(npu_input, repeat=1)
    assert isinstance(out_after_remove, torch.Tensor)
    assert out_after_remove.device.type == "npu"
    assert tuple(out_after_remove.shape) == (2, 3)
    assert len(npu_module.events) == 2
    assert npu_module.events[0][0] == "record_hook"
    assert npu_module.events[1][0] == "forward"
    assert npu_module.events[0][2] == 1
    assert npu_module.events[1][3] == 1


def test_module_register_forward_pre_hook_bound_method_and_kwargs_modification(npu_module, npu_input):
    """验证绑定成员方法 hook、with_kwargs=True 以及对 args/kwargs 的联合修改。"""

    recorder = _BoundMethodHookRecorder()
    handle = npu_module.register_forward_pre_hook(recorder.pre_hook, with_kwargs=True)

    assert isinstance(handle, RemovableHandle)
    assert callable(recorder.pre_hook)

    out = npu_module(npu_input, repeat=1)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert tuple(out.shape) == (3, 6)
    assert len(recorder.events) == 1
    assert recorder.events[0][0] == "bound_method"
    assert recorder.events[0][1] == (2, 3)
    assert recorder.events[0][2] == 1
    assert recorder.events[0][3] == "npu"
    assert len(npu_module.events) == 1
    assert npu_module.events[0][0] == "forward"
    assert npu_module.events[0][1] == (1, 6)
    assert npu_module.events[0][3] == 3

    handle.remove()
    npu_module.events.clear()

    out_after_remove = npu_module(npu_input, repeat=1)
    assert isinstance(out_after_remove, torch.Tensor)
    assert out_after_remove.device.type == "npu"
    assert tuple(out_after_remove.shape) == (2, 3)
    assert len(npu_module.events) == 1
    assert npu_module.events[0][0] == "forward"
    assert npu_module.events[0][1] == (2, 3)
    assert npu_module.events[0][3] == 1


def test_module_register_forward_pre_hook_non_callable_and_hook_raises_type_error(npu_module, npu_input):
    """验证非 callable 入参与 hook 执行时抛出异常的场景。"""

    non_callable_handle = npu_module.register_forward_pre_hook(123)

    assert isinstance(non_callable_handle, RemovableHandle)

    with pytest.raises(TypeError, match="callable"):
        npu_module(npu_input)

    non_callable_handle.remove()

    def failing_hook(module, args):
        raise RuntimeError("hook failed")

    handle = npu_module.register_forward_pre_hook(failing_hook)

    with pytest.raises(RuntimeError, match="hook failed"):
        npu_module(npu_input)

    handle.remove()
