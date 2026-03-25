"""
测试目的：
1. 验证 torch._C.DispatchKey.Functionalize 可访问、可识别，并满足枚举对象的基本语义。
2. 覆盖 Functionalize 作为 DispatchKey 单例成员、类型判断、身份判断、与其他 DispatchKey 的比较，以及 DispatchKeySet 的构造、查询、集合运算和异常分支。
3. 补充 _ExcludeDispatchKeyGuard(DispatchKeySet(Functionalize)) 的真实消费路径，验证其与 FunctionalTensorMode 配合时可正常工作。

API 名称：torch._C.DispatchKey.Functionalize
"""

import pytest

import torch
from torch._subclasses.functional_tensor import FunctionalTensorMode


DispatchKey = torch._C.DispatchKey
DispatchKeySet = torch._C.DispatchKeySet


def _comparison_cases():
    cases = [
        (DispatchKey.Functionalize, True),
        (DispatchKey.CPU, False),
        (DispatchKey.Meta, False),
    ]

    for optional_key_name in ("AutogradCPU", "AutogradPrivateUse1"):
        optional_key = getattr(DispatchKey, optional_key_name, None)
        if optional_key is not None:
            cases.append((optional_key, False))

    return cases


def test_functionalize_attribute_exists_and_isinstance():
    key = DispatchKey.Functionalize

    assert hasattr(DispatchKey, "Functionalize")
    assert isinstance(key, DispatchKey)
    assert key is DispatchKey.Functionalize
    assert key != DispatchKey.CPU
    assert key != DispatchKey.Meta


@pytest.mark.parametrize(
    "other_key, expected_equal",
    _comparison_cases(),
)
def test_functionalize_comparison_with_other_dispatchkeys(other_key, expected_equal):
    key = DispatchKey.Functionalize

    assert (key == other_key) is expected_equal
    assert (key != other_key) is (not expected_equal)


@pytest.mark.parametrize(
    "constructor_arg, expected_key",
    [
        (DispatchKey.Functionalize, DispatchKey.Functionalize),
        (DispatchKey.CPU, DispatchKey.CPU),
        (DispatchKey.Meta, DispatchKey.Meta),
        ("Functionalize", DispatchKey.Functionalize),
        ("CPU", DispatchKey.CPU),
        ("Meta", DispatchKey.Meta),
    ],
)
def test_functionalize_dispatchkeyset_construct_and_has(constructor_arg, expected_key):
    key_set = DispatchKeySet(constructor_arg)

    assert isinstance(key_set, DispatchKeySet)
    assert key_set.has(expected_key) is True

    if expected_key is not DispatchKey.Functionalize:
        assert key_set.has(DispatchKey.Functionalize) is False


def test_functionalize_dispatchkeyset_union_and_intersection():
    func_set = DispatchKeySet(DispatchKey.Functionalize)
    cpu_set = DispatchKeySet("CPU")

    union_set = func_set | cpu_set
    same_intersection = func_set & DispatchKeySet("Functionalize")
    empty_intersection = func_set & cpu_set

    assert union_set.has(DispatchKey.Functionalize) is True
    assert union_set.has(DispatchKey.CPU) is True
    assert same_intersection.has(DispatchKey.Functionalize) is True
    assert empty_intersection.has(DispatchKey.Functionalize) is False
    assert empty_intersection.has(DispatchKey.CPU) is False


def test_functionalize_excluded_dispatch_key_guard_consumption_path():
    unlifted = torch.tensor([0.0])
    maybe_disable = torch._C._ExcludeDispatchKeyGuard(
        DispatchKeySet(DispatchKey.Functionalize)
    )

    assert torch._C._dispatch_tls_local_exclude_set().has(DispatchKey.Functionalize) is False

    with maybe_disable, FunctionalTensorMode():
        assert torch._C._dispatch_tls_local_exclude_set().has(DispatchKey.Functionalize) is True
        lifted = torch.ops.aten.lift_fresh.default(unlifted)

    assert torch._C._dispatch_tls_local_exclude_set().has(DispatchKey.Functionalize) is False
    assert unlifted.untyped_storage() != lifted.untyped_storage()


@pytest.mark.parametrize(
    "bad_arg, expected_exc",
    [
        (None, TypeError),
        (1, TypeError),
        (object(), TypeError),
        ([DispatchKey.Functionalize], TypeError),
        ({"key": DispatchKey.Functionalize}, TypeError),
        ("NotAKey", RuntimeError),
        ("functionalize", RuntimeError),
        ("", RuntimeError),
    ],
)
def test_functionalize_dispatchkeyset_invalid_construction_raises(bad_arg, expected_exc):
    with pytest.raises(expected_exc):
        DispatchKeySet(bad_arg)
