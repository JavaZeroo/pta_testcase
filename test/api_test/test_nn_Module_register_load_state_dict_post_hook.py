"""
测试目的：
1. 验证 torch.nn.Module.register_load_state_dict_post_hook 在 NPU 场景下可正常注册后置 hook，并在 load_state_dict() 后触发。
2. 验证 hook 可修改 incompatible_keys，进而影响 strict=True 的加载结果：清空可避免报错，新增可触发报错。
3. 覆盖普通函数、绑定方法、多个 hook、handle.remove()、None/非 callable、缺省不传等主要参数与异常场景。
4. 验证模型参数与 buffer 均位于 NPU，确保测试路径真实跑在 NPU 设备上。

API 名称：torch.nn.Module.register_load_state_dict_post_hook

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| hook 传入普通函数 | 已覆盖 | 以普通函数注册 post-hook，并验证会被调用 |
| hook 传入绑定方法 | 已覆盖 | 以类实例绑定方法注册 post-hook，并验证会被调用 |
| hook 传入 None | 已覆盖 | 以 None 作为 hook，验证 load_state_dict() 时抛出 TypeError |
| hook 传入非 callable 非 None 对象 | 已覆盖 | 以整数对象作为 hook，验证 load_state_dict() 时抛出 TypeError |
| hook 缺省不传 | 已覆盖 | 直接缺少必填参数调用，验证抛出 TypeError |
| incompatible_keys 为正常对象 | 已覆盖 | 验证包含 missing_keys / unexpected_keys 两个属性且可被读取 |
| incompatible_keys 被修改为清空 | 已覆盖 | hook 清空两个列表后，strict=True 可正常通过 |
| incompatible_keys 被修改为新增 | 已覆盖 | hook 新增缺失/多余键后，strict=True 抛出 RuntimeError |
| 多个 hook 同时注册 | 已覆盖 | 验证多个 post-hook 均会被触发 |
| handle.remove() | 已覆盖 | 移除其中一个 hook 后，再次加载时该 hook 不再触发 |
| 模型设备 | 已覆盖 | 模型参数与 buffer 均位于 NPU |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值正确性 | 本测试聚焦 hook 注册、触发、异常与设备，不做张量数值精确校验 |
| 多 NPU 卡 / 分布式加载 | 当前用例仅验证单卡 NPU 上的基础功能路径，不依赖多卡环境 |
| 复杂嵌套模块树的全量组合回归 | 本测试以最小可复现模型覆盖核心语义，避免引入过多无关结构 |
| 不同 PyTorch/NPU 版本兼容矩阵 | 由 CI 的版本矩阵覆盖，本文件只验证当前环境的功能行为 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Module.register_load_state_dict_post_hook 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Module.register_load_state_dict_post_hook 测试。")


class _DemoNet(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = torch.nn.Linear(4, 3)
        self.relu = torch.nn.ReLU()
        self.fc2 = torch.nn.Linear(3, 2)
        self.register_buffer("scale", torch.tensor([1.0]))

    def forward(self, x):
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        return x * self.scale


class _HookRecorder:
    def __init__(self):
        self.calls = []

    def hook(self, module, incompatible_keys):
        self.calls.append((module, incompatible_keys))


@pytest.fixture()
def npu_model():
    _require_npu()
    model = _DemoNet().to(torch.device("npu:0"))
    assert all(param.device.type == "npu" for param in model.parameters())
    assert all(buf.device.type == "npu" for buf in model.buffers())
    return model


@pytest.fixture()
def npu_state_dict_with_mismatch(npu_model):
    state_dict = {k: v.clone() for k, v in npu_model.state_dict().items()}
    removed_key = next(iter(state_dict))
    state_dict.pop(removed_key)
    state_dict["unexpected.weight"] = torch.ones(1, device=torch.device("npu:0"))
    return state_dict, removed_key


@pytest.fixture()
def npu_state_dict_matched(npu_model):
    return {k: v.clone() for k, v in npu_model.state_dict().items()}


def test_register_load_state_dict_post_hook_missing_required_argument_raises_type_error(npu_model):
    """验证必填参数缺省不传时会抛出 TypeError。"""
    with pytest.raises(TypeError):
        npu_model.register_load_state_dict_post_hook()


def test_register_load_state_dict_post_hook_function_and_incompatible_keys(npu_model, npu_state_dict_with_mismatch):
    """验证普通函数 hook、load_state_dict() 后触发以及 incompatible_keys 对象属性。"""
    state_dict, removed_key = npu_state_dict_with_mismatch
    hook_called = {"flag": False}
    hook_records = []

    def hook(module, incompatible_keys):
        hook_called["flag"] = True
        hook_records.append((module, incompatible_keys))

    assert callable(hook)

    handle = npu_model.register_load_state_dict_post_hook(hook)
    assert handle is not None
    assert hasattr(handle, "remove")
    assert isinstance(handle, torch.utils.hooks.RemovableHandle)

    load_result = npu_model.load_state_dict(state_dict, strict=False)

    assert hook_called["flag"] is True
    assert len(hook_records) == 1
    hooked_module, incompatible_keys = hook_records[0]
    assert hooked_module is npu_model
    assert hasattr(incompatible_keys, "missing_keys")
    assert hasattr(incompatible_keys, "unexpected_keys")
    assert isinstance(incompatible_keys.missing_keys, list)
    assert isinstance(incompatible_keys.unexpected_keys, list)
    assert removed_key in incompatible_keys.missing_keys
    assert "unexpected.weight" in incompatible_keys.unexpected_keys
    assert hasattr(load_result, "missing_keys")
    assert hasattr(load_result, "unexpected_keys")
    assert npu_model.fc1.weight.device.type == "npu"
    assert npu_model.fc2.bias.device.type == "npu"


def test_register_load_state_dict_post_hook_clear_incompatible_keys_allows_strict_true(npu_model, npu_state_dict_with_mismatch):
    """验证 hook 清空 incompatible_keys 后，strict=True 不再报错。"""
    state_dict, _ = npu_state_dict_with_mismatch

    def clear_hook(module, incompatible_keys):
        assert module is npu_model
        incompatible_keys.missing_keys.clear()
        incompatible_keys.unexpected_keys.clear()

    handle = npu_model.register_load_state_dict_post_hook(clear_hook)
    assert handle is not None

    load_result = npu_model.load_state_dict(state_dict, strict=True)
    assert load_result.missing_keys == []
    assert load_result.unexpected_keys == []


def test_register_load_state_dict_post_hook_add_incompatible_keys_raises_runtime_error(npu_model, npu_state_dict_matched):
    """验证完全匹配的 state_dict 可因 hook 新增 incompatible_keys 而在 strict=True 下报错。"""
    state_dict = npu_state_dict_matched
    hook_called = []

    def add_hook(module, incompatible_keys):
        assert module is npu_model
        incompatible_keys.missing_keys.append("added_missing_key")
        incompatible_keys.unexpected_keys.append("added_unexpected_key")
        hook_called.append(True)

    handle = npu_model.register_load_state_dict_post_hook(add_hook)
    assert handle is not None

    with pytest.raises(RuntimeError):
        npu_model.load_state_dict(state_dict, strict=True)

    assert hook_called == [True]


def test_register_load_state_dict_post_hook_callable_with_wrong_signature_raises_type_error(
    npu_model, npu_state_dict_matched
):
    """验证可调用但参数个数不匹配的 hook 在 load_state_dict() 时抛出 TypeError。"""

    def bad_signature_hook(module):
        return module

    handle = npu_model.register_load_state_dict_post_hook(bad_signature_hook)
    assert handle is not None

    with pytest.raises(TypeError):
        npu_model.load_state_dict(npu_state_dict_matched)


def test_register_load_state_dict_post_hook_multiple_hooks_and_remove(npu_model, npu_state_dict_with_mismatch):
    """验证多个 hook 同时注册、均能触发，以及 handle.remove() 后不再触发。"""
    state_dict, _ = npu_state_dict_with_mismatch

    function_calls = []
    recorder = _HookRecorder()

    def function_hook(module, incompatible_keys):
        function_calls.append((module, incompatible_keys))

    handle1 = npu_model.register_load_state_dict_post_hook(function_hook)
    handle2 = npu_model.register_load_state_dict_post_hook(recorder.hook)
    assert handle1 is not None
    assert handle2 is not None
    assert hasattr(handle1, "remove")
    assert hasattr(handle2, "remove")

    npu_model.load_state_dict(state_dict, strict=False)
    assert len(function_calls) == 1
    assert len(recorder.calls) == 1
    assert function_calls[0][0] is npu_model
    assert recorder.calls[0][0] is npu_model
    assert hasattr(function_calls[0][1], "missing_keys")
    assert hasattr(recorder.calls[0][1], "unexpected_keys")

    handle1.remove()
    npu_model.load_state_dict(state_dict, strict=False)
    assert len(function_calls) == 1
    assert len(recorder.calls) == 2

    handle2.remove()


@pytest.mark.parametrize("bad_hook", [None, 123])
def test_register_load_state_dict_post_hook_non_callable_raises_type_error(npu_model, bad_hook):
    """验证 None / 非 callable hook 在 load_state_dict() 触发时抛出 TypeError。"""
    handle = npu_model.register_load_state_dict_post_hook(bad_hook)
    assert handle is not None

    with pytest.raises(TypeError):
        npu_model.load_state_dict(npu_model.state_dict())
