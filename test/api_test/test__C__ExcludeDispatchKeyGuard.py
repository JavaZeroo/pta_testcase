"""
测试目的：
1. 验证 torch._C._ExcludeDispatchKeyGuard 可使用 DispatchKeySet 正常构造，并且能在 NPU 环境中作为上下文管理器工作。
2. 验证参数传入/不传、None/非 None、单枚举/多枚举等主要入参形态的覆盖。
3. 验证非法入参会抛出异常，并覆盖上下文管理器在正常路径和异常路径下的 __enter__/__exit__ 行为。
4. 通过 torch_npu 与 NPU 张量创建进行环境门禁，确保所有测试都在 NPU 上运行。

API 名称：torch._C._ExcludeDispatchKeyGuard

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 1. 构造入参传入 DispatchKeySet | 已覆盖 | 覆盖单个 DispatchKeySet 以及多个 DispatchKey 组合成的 DispatchKeySet |
| 2. 构造入参传入单个 DispatchKey 包装后的 DispatchKeySet | 已覆盖 | 覆盖 CPU、PrivateUse1、AutogradPrivateUse1、Functionalize、ADInplaceOrView 等代表性枚举 |
| 3. 构造入参不传 | 已覆盖 | 调用无参构造，验证 TypeError |
| 4. 构造入参为 None | 已覆盖 | 调用 ExcludeDispatchKeyGuard(None)，验证 TypeError |
| 5. 构造入参为其他非法类型 | 已覆盖 | 覆盖 int、str、list、dict、tuple 等错误入参 |
| 6. 作为上下文管理器使用 | 已覆盖 | 通过 with 语句覆盖 __enter__/__exit__ 正常路径 |
| 7. 上下文管理器异常路径 | 已覆盖 | 在 with 语句内部抛出 RuntimeError，验证 __exit__ 可正常参与异常传播 |
| 8. NPU 环境守卫 | 已覆盖 | 在测试前检查 torch.npu 是否可用，并创建 NPU 张量作为运行环境校验 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 所有 DispatchKey 枚举的穷举覆盖 | 仅选择 CPU、PrivateUse1、AutogradPrivateUse1、Functionalize、ADInplaceOrView 作为代表性枚举，避免测试冗余 |
| 内部 dispatch key 栈变化的实现细节 | 本测试聚焦公开接口与上下文管理器语义，不验证内部实现细节 |
| 多卡或分布式 NPU 场景 | 本测试聚焦单卡、单进程功能接口，不依赖分布式环境 |
| 精确数值正确性校验 | 该 API 主要验证构造和上下文行为，不做具体数值正确性校验 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


DispatchKeySet = torch._C.DispatchKeySet
DispatchKey = torch._C.DispatchKey
ExcludeDispatchKeyGuard = torch._C._ExcludeDispatchKeyGuard


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 _ExcludeDispatchKeyGuard 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 _ExcludeDispatchKeyGuard 测试。")
    if not hasattr(torch._C, "_ExcludeDispatchKeyGuard"):
        pytest.skip("当前 PyTorch 版本未提供 torch._C._ExcludeDispatchKeyGuard，无法执行该 API 测试。")


@pytest.fixture()
def npu_guard():
    _require_npu()
    probe = torch.ones((1,), device=torch.device("npu:0"))
    assert probe.device.type == "npu"
    return probe


def _make_npu_tensor(size):
    tensor = torch.ones(size, device=torch.device("npu:0"))
    assert tensor.device.type == "npu"
    return tensor


def test_exclude_dispatch_key_guard_construct_with_dispatchkeyset_and_context_manager(npu_guard):
    """验证使用 DispatchKeySet 构造 guard，并作为上下文管理器进入/退出。"""
    key_set = DispatchKeySet(DispatchKey.CPU) | DispatchKeySet(DispatchKey.PrivateUse1)
    guard = ExcludeDispatchKeyGuard(key_set)

    assert guard is not None
    with guard as enter_result:
        assert enter_result is None
        _make_npu_tensor((2,))

    _make_npu_tensor((1,))


@pytest.mark.parametrize(
    "dispatch_key",
    [
        DispatchKey.CPU,
        DispatchKey.PrivateUse1,
        DispatchKey.AutogradPrivateUse1,
        DispatchKey.Functionalize,
        DispatchKey.ADInplaceOrView,
    ],
)
def test_exclude_dispatch_key_guard_construct_from_single_dispatch_key_wrapped_in_set(npu_guard, dispatch_key):
    """验证单个 DispatchKey 包装成 DispatchKeySet 后可用于构造 guard。"""
    key_set = DispatchKeySet(dispatch_key)
    with ExcludeDispatchKeyGuard(key_set):
        _make_npu_tensor((3,))


@pytest.mark.parametrize(
    "dispatch_key",
    [
        DispatchKey.CPU,
        DispatchKey.Functionalize,
    ],
)
def test_exclude_dispatch_key_guard_direct_dispatch_key_raises_type_error(npu_guard, dispatch_key):
    """验证直接传入 DispatchKey 而非 DispatchKeySet 时会抛出 TypeError。"""
    with pytest.raises(TypeError):
        ExcludeDispatchKeyGuard(dispatch_key)


def test_exclude_dispatch_key_guard_missing_argument_raises_type_error(npu_guard):
    """验证构造函数不传参数时会抛出 TypeError。"""
    with pytest.raises(TypeError):
        ExcludeDispatchKeyGuard()


@pytest.mark.parametrize(
    "bad_arg",
    [
        None,
        1,
        "invalid",
        [],
        {},
        (),
    ],
)
def test_exclude_dispatch_key_guard_invalid_arguments_raise(npu_guard, bad_arg):
    """验证非法入参会抛出 TypeError。"""
    with pytest.raises(TypeError):
        ExcludeDispatchKeyGuard(bad_arg)


def test_exclude_dispatch_key_guard_context_manager_exception_path(npu_guard):
    """验证上下文管理器在异常路径下仍可正常退出并传播异常。"""
    key_set = DispatchKeySet(DispatchKey.AutogradPrivateUse1)
    with pytest.raises(RuntimeError):
        with ExcludeDispatchKeyGuard(key_set):
            _make_npu_tensor((4,))
            raise RuntimeError("intentional error for __exit__ path")
