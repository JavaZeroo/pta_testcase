"""
测试目的：
1. 验证 torch.library.impl 在 NPU 环境下可正确注册自定义算子实现，并能通过 torch.ops 在 NPU Tensor 上完成派发。
2. 覆盖 func 传/不传、lib 传/不传、None/非 None、主要类型与枚举值、正常/异常场景、边界值等参数维度。
3. 仅验证注册、调用、设备与类型，不做具体数值正确性校验。

API 名称：torch.library.impl

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| qualname | 已覆盖 | 合法 "namespace::op"；非法格式/类型触发异常 |
| types | 已覆盖 | 单字符串 "NPU"；默认枚举 "default"；字符串序列 ["NPU", "CPU"]；空字符串/非法类型触发异常 |
| func | 已覆盖 | 直接传 callable；传 None 走装饰器；装饰器使用时省略 func；非 callable 触发异常 |
| lib | 已覆盖 | 显式传入 Library；显式传入 None；不传该参数；非法对象触发异常 |
| 输入设备 | 已覆盖 | 仅使用 NPU Tensor 执行算子调用 |
| 场景 | 已覆盖 | 正常注册/调用；异常注册；边界输入（非法字符串、空字符串、序列混合类型） |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值正确性 | 该 API 的重点是注册与派发，本文件仅验证是否成功返回 Tensor/抛出异常，不做数值比对 |
| 其他后端的真实设备执行 | 当前用例聚焦 NPU 功能；为保证测试稳定性，仅在 NPU 环境下运行 |
| 更多复杂装饰器嵌套组合 | 本文件已覆盖直接调用与装饰器两种核心方式，复杂嵌套属于冗余组合 |
"""

import uuid

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.library.impl 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.library.impl 测试。")


def _make_namespace() -> str:
    return f"test_library_impl_{uuid.uuid4().hex}"


def _define_unique_op():
    namespace = _make_namespace()
    lib = torch.library.Library(namespace, "DEF")
    lib.define("myop(Tensor x) -> Tensor")
    return namespace, lib


def _make_npu_tensor():
    return torch.tensor([1.0, 2.0, 3.0], device=torch.device("npu:0"))


@pytest.mark.parametrize("types_arg", ["NPU", "default", ["NPU", "CPU"]])
@pytest.mark.parametrize("lib_mode", ["omitted", "none", "object"])
def test_torch_library_impl_register_and_dispatch_on_npu(types_arg, lib_mode):
    """验证正常场景：不同 types 形态下，func 直接传入、lib 传/不传都能在 NPU 上注册并调用。"""
    _require_npu()

    namespace, lib = _define_unique_op()
    qualname = f"{namespace}::myop"

    def kernel(x):
        assert isinstance(x, torch.Tensor)
        return x

    kwargs = {}
    if lib_mode == "none":
        kwargs["lib"] = None
    elif lib_mode == "object":
        kwargs["lib"] = lib

    registered = torch.library.impl(qualname, types_arg, func=kernel, **kwargs)
    assert registered is None

    op = getattr(torch.ops, namespace).myop
    out = op(_make_npu_tensor())

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == (3,)
    assert out.dtype == torch.float32


@pytest.mark.parametrize("types_arg", ["NPU", "default", ["NPU", "CPU"]])
@pytest.mark.parametrize("lib_mode", ["omitted", "none", "object"])
def test_torch_library_impl_register_by_decorator_on_npu(types_arg, lib_mode):
    """验证装饰器场景：func=None 时，注册器可返回可调用装饰器并在 NPU 上完成派发。"""
    _require_npu()

    namespace, lib = _define_unique_op()
    qualname = f"{namespace}::myop"

    def kernel(x):
        assert x.device.type == "npu"
        return x

    kwargs = {}
    if lib_mode == "none":
        kwargs["lib"] = None
    elif lib_mode == "object":
        kwargs["lib"] = lib

    decorator = torch.library.impl(qualname, types_arg, func=None, **kwargs)
    assert callable(decorator)
    assert decorator(kernel) is None

    op = getattr(torch.ops, namespace).myop
    out = op(_make_npu_tensor())

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == (3,)


@pytest.mark.parametrize("types_arg", ["NPU", "default", ["NPU", "CPU"]])
@pytest.mark.parametrize("lib_mode", ["omitted", "none", "object"])
def test_torch_library_impl_register_by_decorator_without_func_kwarg_on_npu(types_arg, lib_mode):
    """验证装饰器场景：省略 func 参数时，API 仍可完成注册并在 NPU 上派发。"""
    _require_npu()

    namespace, lib = _define_unique_op()
    qualname = f"{namespace}::myop"

    kwargs = {}
    if lib_mode == "none":
        kwargs["lib"] = None
    elif lib_mode == "object":
        kwargs["lib"] = lib

    @torch.library.impl(qualname, types_arg, **kwargs)
    def kernel(x):
        assert x.device.type == "npu"
        return x

    assert kernel is None

    op = getattr(torch.ops, namespace).myop
    out = op(_make_npu_tensor())

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == (3,)


@pytest.mark.parametrize("bad_qualname", [None, 123, "badname", "a::", "::op"])
def test_torch_library_impl_invalid_qualname_raises(bad_qualname):
    """验证 qualname 非法类型或格式时，API 会抛出异常。"""
    _require_npu()

    namespace, lib = _define_unique_op()

    def kernel(x):
        return x

    with pytest.raises((TypeError, ValueError, RuntimeError, AttributeError)):
        torch.library.impl(bad_qualname, "NPU", func=kernel, lib=lib)

    # 继续验证同一个 lib 在异常后仍可正常注册。
    torch.library.impl(f"{namespace}::myop", "NPU", func=kernel, lib=lib)
    out = getattr(torch.ops, namespace).myop(_make_npu_tensor())
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"


@pytest.mark.parametrize("bad_func", [123, "abc", object()])
def test_torch_library_impl_non_callable_func_raises(bad_func):
    """验证 func 非 callable 时，使用 pytest.raises 捕获异常。"""
    _require_npu()

    namespace, lib = _define_unique_op()

    with pytest.raises((TypeError, RuntimeError)):
        torch.library.impl(f"{namespace}::myop", "NPU", func=bad_func, lib=lib)

    # 非法 func 不应影响后续正常注册。
    def kernel(x):
        return x

    torch.library.impl(f"{namespace}::myop", "NPU", func=kernel, lib=lib)
    out = getattr(torch.ops, namespace).myop(_make_npu_tensor())
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"


@pytest.mark.parametrize("bad_types", ["", 123, ["NPU", 123], ["CPU", 123]])
def test_torch_library_impl_invalid_types_raises(bad_types):
    """验证 types 的主要边界值与非法组合会触发异常。"""
    _require_npu()

    namespace, lib = _define_unique_op()

    def kernel(x):
        return x

    with pytest.raises((TypeError, ValueError, RuntimeError)):
        torch.library.impl(f"{namespace}::myop", bad_types, func=kernel, lib=lib)


@pytest.mark.parametrize("bad_lib", [object(), "not_a_library", 123])
def test_torch_library_impl_invalid_lib_raises(bad_lib):
    """验证 lib 非法时会触发异常。"""
    _require_npu()

    namespace, _ = _define_unique_op()

    def kernel(x):
        return x

    with pytest.raises((AttributeError, TypeError, RuntimeError)):
        torch.library.impl(f"{namespace}::myop", "NPU", func=kernel, lib=bad_lib)
