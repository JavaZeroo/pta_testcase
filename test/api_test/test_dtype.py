"""
测试目的：
1. 验证 torch.dtype 作为 PyTorch 数据类型对象的基础属性、身份识别与比较行为。
2. 验证主要 dtype 枚举可用于 tensor 创建，且创建结果的 dtype 与传入 dtype 一致。
3. 验证 dtype 参数传入、显式传 None、以及省略 dtype 的行为差异；同时验证非法 dtype 入参与 torch.dtype 构造行为会抛出异常。

API 名称：torch.dtype

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| dtype 实例枚举 | 已覆盖 | float32 / float64 / float16 / bfloat16 / int8 / int16 / int32 / int64 / bool / uint8 / complex64 / complex128，以及版本可用时的更多 dtype 枚举 |
| isinstance 检查 | 已覆盖 | 覆盖 torch.dtype 对象本身及 tensor.dtype 的 isinstance 判断 |
| dtype 相等/不等比较 | 已覆盖 | 覆盖同一 dtype 的相等性与不同 dtype 的不等性 |
| dtype 作为 tensor 创建参数 | 已覆盖 | 通过 torch.tensor(..., dtype=...) 创建不同 dtype 的 Tensor |
| dtype=None / 省略 dtype | 已覆盖 | 验证显式传 None 与省略 dtype 时的行为一致性 |
| dtype 属性 | 已覆盖 | is_floating_point / is_complex / is_signed / itemsize |
| 异常输入 | 已覆盖 | torch.dtype() / torch.dtype("...") / torch.tensor(..., dtype="...") / torch.tensor(..., dtype=object()) |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 数值正确性 | 本文件聚焦 torch.dtype 的对象行为，不做张量具体数值比对 |
| dtype 别名/历史兼容写法 | 主要枚举已覆盖，别名行为与本 API 的核心功能关系较弱，且不同版本差异较大 |
| 通过其他算子间接生成的 dtype 行为 | 本文件重点覆盖 torch.dtype 与 torch.tensor 的基础用法，不扩展到所有算子路径 |
"""

import pytest

import torch


_DTYPE_CASES = [
    (torch.float32, True, False, True, 4, 1.5),
    (torch.float64, True, False, True, 8, 1.5),
    (torch.float16, True, False, True, 2, 1.5),
    (torch.bfloat16, True, False, True, 2, 1.5),
    (torch.int8, False, False, True, 1, 3),
    (torch.int16, False, False, True, 2, 3),
    (torch.int32, False, False, True, 4, 3),
    (torch.int64, False, False, True, 8, 3),
    (torch.bool, False, False, False, 1, True),
    (torch.uint8, False, False, False, 1, 3),
    (torch.complex64, False, True, True, 8, 1 + 2j),
    (torch.complex128, False, True, True, 16, 1 + 2j),
]

_ENUM_DTYPE_NAMES = [
    "bool",
    "uint8",
    "int8",
    "int16",
    "int32",
    "int64",
    "float16",
    "float32",
    "float64",
    "bfloat16",
    "complex64",
    "complex128",
    "uint16",
    "uint32",
    "uint64",
    "complex32",
    "float8_e4m3fn",
    "float8_e4m3fnuz",
    "float8_e5m2",
    "float8_e5m2fnuz",
]


def _iter_available_dtype_enums():
    for name in _ENUM_DTYPE_NAMES:
        dtype = getattr(torch, name, None)
        if isinstance(dtype, torch.dtype):
            yield name, dtype


def _create_tensor_for_dtype(dtype):
    for case_dtype, _, _, _, _, sample in _DTYPE_CASES:
        if case_dtype is dtype:
            try:
                return torch.tensor(sample, dtype=dtype)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                if any(
                    key in msg
                    for key in (
                        "not supported",
                        "unsupported",
                        "not implemented",
                        "cannot create",
                        "cannot convert",
                    )
                ):
                    pytest.skip(f"当前后端不支持 dtype={dtype} 的 tensor 创建：{exc}")
                raise
    raise AssertionError(f"未找到 dtype 对应的样本值：{dtype}")


@pytest.mark.parametrize("dtype, is_floating_point, is_complex, is_signed, itemsize, _sample", _DTYPE_CASES)
def test_dtype_attributes_and_isinstance(dtype, is_floating_point, is_complex, is_signed, itemsize, _sample):
    """验证 dtype 对象属性、isinstance 判断，以及 tensor.dtype 与 dtype 的一致性。"""
    assert isinstance(dtype, torch.dtype)
    assert type(dtype) is torch.dtype
    assert dtype == dtype

    assert dtype.is_floating_point is is_floating_point
    assert dtype.is_complex is is_complex
    assert dtype.is_signed is is_signed
    assert dtype.itemsize == itemsize

    tensor = _create_tensor_for_dtype(dtype)

    assert isinstance(tensor, torch.Tensor)
    assert isinstance(tensor.dtype, torch.dtype)
    assert tensor.dtype == dtype
    assert tensor.dtype is dtype


@pytest.mark.parametrize("dtype_name,dtype", list(_iter_available_dtype_enums()))
def test_dtype_enum_instances(dtype_name, dtype):
    """验证版本可用的 dtype 枚举值均为 torch.dtype 实例。"""
    assert isinstance(dtype, torch.dtype), f"{dtype_name} 应为 torch.dtype 实例"
    assert type(dtype) is torch.dtype


@pytest.mark.parametrize(
    "left,right,should_equal",
    [
        (torch.float32, torch.float32, True),
        (torch.float32, torch.float64, False),
        (torch.int32, torch.int64, False),
        (torch.bool, torch.uint8, False),
        (torch.complex64, torch.complex128, False),
        (torch.float16, torch.bfloat16, False),
    ],
)
def test_dtype_equality_and_inequality(left, right, should_equal):
    """验证主要 dtype 枚举之间的相等/不等比较行为。"""
    if should_equal:
        assert left == right
        assert left is right
    else:
        assert left != right
        assert left is not right


def test_dtype_can_be_used_as_tensor_dtype_argument():
    """验证可使用主要 dtype 创建 Tensor，且 tensor.dtype 与传入 dtype 一致。"""
    for dtype, _, _, _, _, _ in _DTYPE_CASES:
        tensor = _create_tensor_for_dtype(dtype)
        assert isinstance(tensor, torch.Tensor)
        assert tensor.dtype == dtype
        assert tensor.dtype is dtype


@pytest.mark.parametrize(
    "sample",
    [
        [1],
        [1.5],
        [True],
    ],
)
def test_dtype_none_equals_omitted(sample):
    """验证显式传入 dtype=None 与省略 dtype 时的 dtype 推断结果一致。"""
    tensor_omitted = torch.tensor(sample)
    tensor_none = torch.tensor(sample, dtype=None)

    assert isinstance(tensor_omitted.dtype, torch.dtype)
    assert isinstance(tensor_none.dtype, torch.dtype)
    assert tensor_omitted.dtype == tensor_none.dtype


def test_dtype_is_not_callable_as_constructor():
    """验证 torch.dtype 不能作为构造器调用。"""
    with pytest.raises(TypeError):
        torch.dtype()

    with pytest.raises(TypeError):
        torch.dtype("float32")


def test_tensor_invalid_dtype_string_raises():
    """验证 torch.tensor 使用非法 dtype 字符串时抛出异常。"""
    with pytest.raises(TypeError):
        torch.tensor([1], dtype="float32")


def test_tensor_invalid_dtype_object_raises():
    """验证 torch.tensor 使用非法 dtype 对象时抛出异常。"""
    with pytest.raises(TypeError):
        torch.tensor([1], dtype=object())
