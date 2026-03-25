"""
测试目的：
1. 验证 torch._C.DispatchKeySet 在 NPU 环境下可正常构造，并覆盖常见集合运算与成员查询行为。
2. 覆盖参数传入/不传入、None/非None、主要 DispatchKey 枚举、主要返回类型、正常/异常场景。
3. 使用 NPU 张量并执行基础 NPU 算子，确保测试确实在 NPU 环境下执行。

API 名称：torch._C.DispatchKeySet

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 1. 构造参数传入 | 已覆盖 | 单个 DispatchKey 传入构造 DispatchKeySet |
| 2. 构造参数不传入 | 已覆盖 | DispatchKeySet() 触发 TypeError |
| 3. 参数为 None / 非 None | 已覆盖 | None、非 None 的有效 DispatchKey 分别覆盖 |
| 4. 主要枚举值 | 已覆盖 | CPU、PrivateUse1、AutogradCPU、AutogradPrivateUse1 |
| 5. 集合运算（add / | / & / -） | 已覆盖 | 覆盖正常集合、空集合、组合集合 |
| 6. 成员判断/结果类型 | 已覆盖 | has()、highestPriorityTypeId()、raw_repr()、repr() |
| 7. 异常场景 | 已覆盖 | 构造、方法入参类型错误、None 入参错误 |
| 8. 字符串 key 名构造 | 已覆盖 | 验证可通过字符串 key 名正常构造 DispatchKeySet |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 从字符串 key 名构造 DispatchKeySet 的内部/测试专用 key 名 | 本测试仅覆盖稳定主 key 名，避免引入版本相关脆弱断言 |
| 底层位图/内部实现细节 | 本测试聚焦公开接口与集合语义，不验证内部实现细节 |
| 多卡/分布式 NPU 行为 | 本测试聚焦单进程 NPU 功能接口，不依赖多卡环境 |
"""

import pytest

import torch
try:
    import torch_npu  # noqa: F401
except ImportError:
    pytest.skip("torch_npu 未安装，无法在 NPU 环境下执行 DispatchKeySet 测试。", allow_module_level=True)


if not hasattr(torch._C, "DispatchKeySet") or not hasattr(torch._C, "DispatchKey"):
    pytest.skip("当前构建缺少 torch._C.DispatchKeySet 或 torch._C.DispatchKey，跳过测试。", allow_module_level=True)


DispatchKeySet = torch._C.DispatchKeySet
DispatchKey = torch._C.DispatchKey


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 DispatchKeySet 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 DispatchKeySet 测试。")


@pytest.fixture()
def npu_guard():
    _require_npu()
    tensor = torch.tensor([1], device=torch.device("npu:0"))
    assert tensor.device.type == "npu"
    tensor = tensor + 1
    assert tensor.device.type == "npu"
    return tensor


@pytest.mark.parametrize(
    "key",
    [
        DispatchKey.CPU,
        DispatchKey.PrivateUse1,
        DispatchKey.AutogradCPU,
        DispatchKey.AutogradPrivateUse1,
    ],
)
def test_dispatchkeyset_construct_and_introspection(npu_guard, key):
    """验证从单个 DispatchKey 构造 DispatchKeySet，并检查常见只读接口。"""
    _ = npu_guard
    key_set = DispatchKeySet(key)

    assert isinstance(key_set, DispatchKeySet)
    assert key_set.has(key) is True
    assert isinstance(repr(key_set), str)
    assert isinstance(key_set.raw_repr(), int)

    highest = key_set.highestPriorityTypeId()
    assert isinstance(highest, type(DispatchKey.CPU))
    assert key_set.has(highest) is True


def test_dispatchkeyset_constructor_without_argument_raises(npu_guard):
    """验证 DispatchKeySet() 不传参数时会抛出异常。"""
    _ = npu_guard
    with pytest.raises(TypeError):
        DispatchKeySet()


@pytest.mark.parametrize(
    "bad_arg",
    [
        None,
        1,
        [],
        object(),
    ],
)
def test_dispatchkeyset_constructor_invalid_argument_raises(npu_guard, bad_arg):
    """验证非法构造参数会抛出异常。"""
    _ = npu_guard
    with pytest.raises(TypeError):
        DispatchKeySet(bad_arg)


def test_dispatchkeyset_add_remove_and_binary_ops(npu_guard):
    """验证 add / remove / | / & / - 的正常集合语义。"""
    _ = npu_guard

    cpu_set = DispatchKeySet(DispatchKey.CPU)
    npu_set = DispatchKeySet(DispatchKey.PrivateUse1)
    autograd_npu_set = DispatchKeySet(DispatchKey.AutogradPrivateUse1)

    # add 返回新集合，不修改原集合
    added_set = cpu_set.add(DispatchKey.PrivateUse1)
    assert isinstance(added_set, DispatchKeySet)
    assert added_set.has(DispatchKey.CPU) is True
    assert added_set.has(DispatchKey.PrivateUse1) is True
    assert cpu_set.has(DispatchKey.PrivateUse1) is False

    # | 形成组合集合
    union_set = cpu_set | npu_set | autograd_npu_set
    assert isinstance(union_set, DispatchKeySet)
    assert union_set.has(DispatchKey.CPU) is True
    assert union_set.has(DispatchKey.PrivateUse1) is True
    assert union_set.has(DispatchKey.AutogradPrivateUse1) is True

    # & 形成相交集合
    intersection_set = union_set & npu_set
    assert isinstance(intersection_set, DispatchKeySet)
    assert intersection_set.has(DispatchKey.PrivateUse1) is True
    assert intersection_set.has(DispatchKey.CPU) is False

    # - 形成差集
    difference_set = union_set - npu_set
    assert isinstance(difference_set, DispatchKeySet)
    assert difference_set.has(DispatchKey.PrivateUse1) is False
    assert difference_set.has(DispatchKey.AutogradPrivateUse1) is True

    # remove 返回新集合，不修改原集合
    removed_set = union_set.remove(DispatchKey.CPU)
    assert isinstance(removed_set, DispatchKeySet)
    assert removed_set.has(DispatchKey.CPU) is False
    assert removed_set.has(DispatchKey.AutogradPrivateUse1) is True
    assert union_set.has(DispatchKey.CPU) is True


@pytest.mark.parametrize(
    "constructor_arg",
    [
        "CPU",
        "PrivateUse1",
    ],
)
def test_dispatchkeyset_construct_from_string_name(npu_guard, constructor_arg):
    """验证可通过字符串 key 名正常构造 DispatchKeySet。"""
    _ = npu_guard

    key_set = DispatchKeySet(constructor_arg)

    assert isinstance(key_set, DispatchKeySet)
    assert key_set.has(getattr(DispatchKey, constructor_arg)) is True


def test_dispatchkeyset_empty_result_boundary_case(npu_guard):
    """验证集合运算得到空结果集时的边界行为。"""
    _ = npu_guard

    cpu_set = DispatchKeySet(DispatchKey.CPU)
    empty_set = cpu_set - cpu_set

    assert isinstance(empty_set, DispatchKeySet)
    assert empty_set.has(DispatchKey.CPU) is False


@pytest.mark.parametrize(
    "method_name",
    ["add", "has", "remove"],
)
def test_dispatchkeyset_method_without_argument_raises(npu_guard, method_name):
    """验证主要实例方法在不传参数时会抛出异常。"""
    _ = npu_guard
    key_set = DispatchKeySet(DispatchKey.CPU)

    method = getattr(key_set, method_name)
    with pytest.raises(TypeError):
        method()


@pytest.mark.parametrize(
    "method_name",
    ["add", "has", "remove"],
)
def test_dispatchkeyset_method_none_argument_raises(npu_guard, method_name):
    """验证主要实例方法传入 None 时会抛出异常。"""
    _ = npu_guard
    key_set = DispatchKeySet(DispatchKey.CPU)

    method = getattr(key_set, method_name)
    with pytest.raises(TypeError):
        method(None)


@pytest.mark.parametrize(
    "bad_operand",
    [None, 1, object()],
)
def test_dispatchkeyset_binary_operator_invalid_operand_raises(npu_guard, bad_operand):
    """验证二元运算符在传入非 DispatchKeySet 参数时抛出异常。"""
    _ = npu_guard
    key_set = DispatchKeySet(DispatchKey.CPU)

    with pytest.raises(TypeError):
        _ = key_set | bad_operand

    with pytest.raises(TypeError):
        _ = key_set & bad_operand

    with pytest.raises(TypeError):
        _ = key_set - bad_operand
