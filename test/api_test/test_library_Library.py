"""
测试目的：
1. 验证 torch.library.Library 在 NPU 环境下可正常构造，并可用于定义/实现自定义算子。
2. 覆盖构造参数 ns、kind、dispatch_key，以及 define() / impl() 的主要参数维度与异常场景。
3. 验证在 NPU 张量上调用自定义算子时，注册链路可正常生效。

API 名称：torch.library.Library

参数维度覆盖表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| ns | 已覆盖 | 覆盖非空唯一 namespace，以及空字符串 namespace 边界值 |
| kind | 已覆盖 | 覆盖 DEF / IMPL / FRAGMENT 三种主要枚举值，以及非法 kind 异常 |
| dispatch_key（构造） | 已覆盖 | 覆盖默认不传与显式传入 PrivateUse1 两种情况 |
| define(schema) | 已覆盖 | 覆盖正常 schema、非法 schema、重复 define 异常 |
| define(alias_analysis) | 已覆盖 | 覆盖默认值与 “CONSERVATIVE” 两种主要取值 |
| define(tags) | 已覆盖 | 覆盖不传、单个 torch.Tag.pt2_compliant_tag，以及 list[Tag] / tuple[Tag] 两种主要序列类型 |
| impl(op_name) | 已覆盖 | 覆盖字符串 op_name、OpOverload 对象两种主要类型，以及非法类型异常 |
| impl(dispatch_key) | 已覆盖 | 覆盖默认继承 Library 构造值与显式传入 PrivateUse1 |
| impl(with_keyset) | 已覆盖 | 覆盖默认 False 与显式 True |
| NPU 张量调用 | 已覆盖 | 覆盖自定义算子在 npu:0 上的正常调用 |
| 异常场景 | 已覆盖 | 覆盖非法 kind、非法 schema、重复 define、非法 op_name 类型等 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| None 入参场景 | 该 API 主要参数为字符串/枚举/回调函数，当前签名未提供稳定的 None 语义，强行覆盖容易引入无意义失败 |
| fallback 的真实后端调度 | torch_npu 运行时可能已占用相同后端 fallback 注册点，直接验证真实 fallback 调度存在冲突风险；本文件聚焦 Library 的基础构造、define/impl 主链路 |
| 其他后端 dispatch_key（如 CPU/CUDA）的真实执行 | 本文件目标是 NPU 功能测试，其他后端不作为本次验证重点 |
| 多卡 / 跨卡切换 | 当前测试仅验证单卡 NPU 基础功能，避免依赖特定多卡环境 |
| 数值精度正确性 | 本测试仅验证注册与调度行为，不做具体数值正确性校验 |
"""

import pytest

import torch
import torch_npu  # noqa: F401

from torch.library import Library


def _require_npu() -> None:
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法执行 torch.library.Library 的 NPU 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法执行 torch.library.Library 的 NPU 测试。")


@pytest.fixture()
def npu_tensor():
    _require_npu()
    return torch.ones((2, 3), device=torch.device("npu:0"))


def _unique_ns(prefix: str) -> str:
    import uuid

    return f"pta_library_{prefix}_{uuid.uuid4().hex}"


@pytest.mark.parametrize("kind", ["DEF", "IMPL", "FRAGMENT"])
def test_library_constructor_default_dispatch_key_on_npu(kind, npu_tensor):
    """验证构造函数在默认 dispatch_key 下对主要 kind 枚举均可完成注册并在 NPU 上生效。"""
    ns = _unique_ns(f"ctor_default_{kind.lower()}")
    lib = Library(ns, kind)
    op_name = f"ctor_default_{kind.lower()}"

    if kind in ("DEF", "FRAGMENT"):
        lib.define(f"{op_name}(Tensor x) -> Tensor")
        impl_lib = Library(ns, "IMPL", "PrivateUse1")
        impl_lib.impl(op_name, lambda x: x.clone())
    else:
        def_lib = Library(ns, "DEF")
        def_lib.define(f"{op_name}(Tensor x) -> Tensor")
        lib.impl(op_name, lambda x: x.clone(), "PrivateUse1")

    out = getattr(getattr(torch.ops, ns), op_name)(npu_tensor)

    assert isinstance(lib, Library)
    assert callable(lib.define)
    assert callable(lib.impl)
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == npu_tensor.shape


def test_library_constructor_explicit_dispatch_key_on_npu(npu_tensor):
    """验证构造函数显式传入 PrivateUse1 dispatch_key 时可完成注册并在 NPU 上生效。"""
    ns = _unique_ns("ctor_explicit")
    def_lib = Library(ns, "DEF")
    def_lib.define("ctor_explicit(Tensor x) -> Tensor")
    lib = Library(ns, "IMPL", "PrivateUse1")
    lib.impl("ctor_explicit", lambda x: x.clone())
    out = getattr(getattr(torch.ops, ns), "ctor_explicit")(npu_tensor)

    assert isinstance(lib, Library)
    assert callable(lib.define)
    assert callable(lib.impl)
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == npu_tensor.shape


def test_library_define_alias_analysis_tags_and_errors_on_npu(npu_tensor):
    """验证 define() 的正常分支、alias_analysis / tags 主要取值以及异常分支。"""
    ns = _unique_ns("define")
    lib = Library(ns, "DEF")

    op_name_default = lib.define("echo_default(Tensor x) -> Tensor")
    op_name_conservative = lib.define(
        "echo_conservative(Tensor x) -> Tensor",
        alias_analysis="CONSERVATIVE",
        tags=torch.Tag.pt2_compliant_tag,
    )
    op_name_tag_tuple = lib.define(
        "echo_tag_tuple(Tensor x) -> Tensor",
        tags=(torch.Tag.pt2_compliant_tag,),
    )
    op_name_tag_list = lib.define(
        "echo_tag_list(Tensor x) -> Tensor",
        tags=[torch.Tag.pt2_compliant_tag],
    )

    assert op_name_default == "echo_default"
    assert op_name_conservative == "echo_conservative"
    assert op_name_tag_tuple == "echo_tag_tuple"
    assert op_name_tag_list == "echo_tag_list"

    namespace = getattr(torch.ops, ns)
    assert hasattr(namespace, "echo_default")
    assert hasattr(namespace, "echo_conservative")
    assert hasattr(namespace, "echo_tag_tuple")
    assert hasattr(namespace, "echo_tag_list")

    impl_lib = Library(ns, "IMPL", "PrivateUse1")
    for op_name in (
        "echo_default",
        "echo_conservative",
        "echo_tag_tuple",
        "echo_tag_list",
    ):
        impl_lib.impl(op_name, lambda x: x.clone())

    for op_name in (
        "echo_default",
        "echo_conservative",
        "echo_tag_tuple",
        "echo_tag_list",
    ):
        out = getattr(namespace, op_name)(npu_tensor)
        assert isinstance(out, torch.Tensor)
        assert out.device.type == "npu"
        assert out.shape == npu_tensor.shape

    with pytest.raises(RuntimeError):
        lib.define("bad_schema")

    with pytest.raises(RuntimeError):
        lib.define("echo_default(Tensor x) -> Tensor")


def test_library_impl_string_opoverload_with_keyset_and_duplicate_errors_on_npu(
    npu_tensor,
):
    """验证 impl() 支持字符串 / OpOverload 两种 op_name，并覆盖 with_keyset 与重复注册异常。"""
    ns = _unique_ns("impl")
    def_lib = Library(ns, "DEF")
    def_lib.define("string_impl(Tensor x) -> Tensor")
    def_lib.define("overload_impl(Tensor x) -> Tensor")
    def_lib.define("keyset_impl(Tensor x) -> Tensor")
    def_lib.define("duplicate_impl(Tensor x) -> Tensor")

    impl_lib_default = Library(ns, "IMPL", "PrivateUse1")
    impl_lib_explicit = Library(ns, "IMPL")

    def string_impl(x):
        return x.clone()

    def overload_impl(x):
        return x.clone()

    def keyset_impl(keyset, x):
        assert keyset is not None
        return x.clone()

    impl_lib_default.impl("string_impl", string_impl)
    impl_lib_default.impl("duplicate_impl", string_impl)

    overload = getattr(getattr(torch.ops, ns), "overload_impl").default
    impl_lib_explicit.impl(overload, overload_impl, "PrivateUse1")

    impl_lib_explicit.impl("keyset_impl", keyset_impl, "PrivateUse1", with_keyset=True)

    with pytest.raises(RuntimeError):
        Library(ns, "IMPL", "PrivateUse1").impl("duplicate_impl", string_impl)

    out_string = getattr(getattr(torch.ops, ns), "string_impl")(npu_tensor)
    out_overload = getattr(getattr(torch.ops, ns), "overload_impl")(npu_tensor)
    out_keyset = getattr(getattr(torch.ops, ns), "keyset_impl")(npu_tensor)

    for out in (out_string, out_overload, out_keyset):
        assert isinstance(out, torch.Tensor)
        assert out.device.type == "npu"
        assert out.device.index == 0
        assert out.shape == npu_tensor.shape


def test_library_invalid_kind_opname_and_empty_namespace_call_on_npu(npu_tensor):
    """验证非法 kind、非法 op_name 类型以及空 namespace 的边界行为。"""
    ns = _unique_ns("invalid")

    with pytest.raises(ValueError):
        Library(ns, "BAD_KIND")

    lib = Library(ns, "DEF")
    lib.define("valid(Tensor x) -> Tensor")
    impl_lib = Library(ns, "IMPL", "PrivateUse1")

    with pytest.raises(RuntimeError):
        impl_lib.impl(123, lambda x: x)

    empty_ns_lib = Library("", "DEF")
    empty_ns_lib.define("foo(Tensor x) -> Tensor")
    empty_ns_impl = Library("", "IMPL", "PrivateUse1")
    empty_ns_impl.impl("foo", lambda x: x.clone())

    out = getattr(torch.ops, "").foo(npu_tensor)
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == npu_tensor.shape
