"""
测试目的：
1. 验证 Tensor.new_zeros 在 NPU 上可正常创建零张量，且返回结果位于 NPU。
2. 覆盖 size / dtype / device / requires_grad / layout / pin_memory 的传参与不传参、None/非None、主要类型、主要枚举值、正常与异常场景、边界值。
3. 重点检查接口行为、返回张量属性、零值内容与异常抛出。

API 名称：Tensor.new_zeros

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| size | 已覆盖 | int / 可变参数 int... / list / tuple / torch.Size，包含空形状、含 0 边界、负值与非法类型异常 |
| dtype | 已覆盖 | 不传、显式 None、float16、int32、非法类型异常 |
| device | 已覆盖 | 不传、显式 None、显式 npu:0、非法类型异常 |
| requires_grad | 已覆盖 | False / True、非法类型异常，及整型 dtype + True 异常 |
| layout | 已覆盖 | 默认 torch.strided、非默认 torch.sparse_coo、非法类型异常 |
| pin_memory | 已覆盖 | False / True 异常（NPU 上不支持/不适用）、非法类型异常 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 稀疏布局下的逐元素零值校验 | 稀疏张量主要验证 layout、shape、dtype 与设备属性，未在本文件中展开逐元素比较 |
| 多卡/跨卡 NPU 场景 | 当前用例仅验证单卡 NPU 基础功能，不依赖多卡环境 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


NPU_DEVICE = torch.device("npu:0")


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 Tensor.new_zeros 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 Tensor.new_zeros 测试。")


def _expected_shape(size):
    if isinstance(size, int):
        return torch.Size([size])
    return torch.Size(size)


@pytest.fixture()
def npu_base_tensor():
    _require_npu()
    return torch.tensor([[1.0, 2.0], [3.0, 4.0]], device=NPU_DEVICE)


def test_tensor_new_zeros_defaults_without_optional_kwargs(npu_base_tensor):
    """验证未显式传入可选参数时的默认行为。"""
    out = npu_base_tensor.new_zeros((2, 3))

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.device.index == 0
    assert out.shape == torch.Size([2, 3])
    assert out.dtype == npu_base_tensor.dtype
    assert out.layout == torch.strided
    assert out.requires_grad is False
    assert (out == 0).all()


@pytest.mark.parametrize("size", [4, (), (1,), [2, 3], torch.Size([1, 0])])
@pytest.mark.parametrize("dtype_arg", [None, torch.float16])
@pytest.mark.parametrize("device_arg", [None, NPU_DEVICE])
@pytest.mark.parametrize("requires_grad", [False, True])
def test_tensor_new_zeros_normal_cases(
    npu_base_tensor, size, dtype_arg, device_arg, requires_grad
):
    """验证正常输入下的调用、返回类型、形状、dtype、layout、设备与 requires_grad 行为。"""
    out = npu_base_tensor.new_zeros(
        size,
        dtype=dtype_arg,
        device=device_arg,
        requires_grad=requires_grad,
        layout=torch.strided,
        pin_memory=False,
    )

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.device.index == 0
    assert out.shape == _expected_shape(size)
    assert out.requires_grad is requires_grad
    assert out.layout == torch.strided
    if dtype_arg is None:
        assert out.dtype == npu_base_tensor.dtype
    else:
        assert out.dtype == dtype_arg
    assert (out == 0).all()


def test_tensor_new_zeros_varargs_size_form(npu_base_tensor):
    """验证 size 使用可变参数形式传入时的行为。"""
    out = npu_base_tensor.new_zeros(2, 3)

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.device.index == 0
    assert out.shape == torch.Size([2, 3])
    assert out.dtype == npu_base_tensor.dtype
    assert out.layout == torch.strided
    assert out.requires_grad is False
    assert (out == 0).all()


def test_tensor_new_zeros_sparse_layout_on_npu(npu_base_tensor):
    """验证主要枚举值 layout=torch.sparse_coo 在 NPU 上的行为。"""
    out = npu_base_tensor.new_zeros((2, 3), layout=torch.sparse_coo)

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.device.index == 0
    assert out.shape == torch.Size([2, 3])
    assert out.layout == torch.sparse_coo
    assert out.dtype == npu_base_tensor.dtype


def test_tensor_new_zeros_explicit_int_dtype_on_npu(npu_base_tensor):
    """验证显式整型 dtype 的返回类型与 requires_grad 默认值。"""
    out = npu_base_tensor.new_zeros(
        (2, 1),
        dtype=torch.int32,
        device=NPU_DEVICE,
        requires_grad=False,
        layout=torch.strided,
        pin_memory=False,
    )

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.device.index == 0
    assert out.dtype == torch.int32
    assert out.requires_grad is False
    assert out.layout == torch.strided
    assert out.shape == torch.Size([2, 1])
    assert (out == 0).all()


def test_tensor_new_zeros_pin_memory_true_raises_on_npu(npu_base_tensor):
    """验证 pin_memory=True 在 NPU 上的异常行为。"""
    with pytest.raises((RuntimeError, TypeError, NotImplementedError)):
        npu_base_tensor.new_zeros((2, 2), pin_memory=True)


@pytest.mark.parametrize(
    "bad_size, expected_exc",
    [
        (-1, RuntimeError),
        ((-1,), RuntimeError),
        ((1, -2), RuntimeError),
        ("abc", TypeError),
        ((1, "x"), TypeError),
    ],
)
def test_tensor_new_zeros_invalid_size_raises(npu_base_tensor, bad_size, expected_exc):
    """验证 size 非法时通过 pytest.raises 抛出异常。"""
    with pytest.raises(expected_exc):
        npu_base_tensor.new_zeros(bad_size)


def test_tensor_new_zeros_invalid_dtype_type_raises(npu_base_tensor):
    """验证非法 dtype 类型时通过 pytest.raises 抛出异常。"""
    with pytest.raises(TypeError):
        npu_base_tensor.new_zeros((2, 2), dtype="float32")


def test_tensor_new_zeros_invalid_device_type_raises(npu_base_tensor):
    """验证非法 device 类型时通过 pytest.raises 抛出异常。"""
    with pytest.raises((TypeError, RuntimeError)):
        npu_base_tensor.new_zeros((2, 2), device=123)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"requires_grad": "true"},
        {"layout": "strided"},
        {"pin_memory": "false"},
    ],
)
def test_tensor_new_zeros_invalid_optional_kwarg_types_raise(npu_base_tensor, kwargs):
    """验证 requires_grad/layout/pin_memory 非法类型时通过 pytest.raises 抛出异常。"""
    with pytest.raises(TypeError):
        npu_base_tensor.new_zeros((2, 2), **kwargs)


def test_tensor_new_zeros_requires_grad_with_int_dtype_raises(npu_base_tensor):
    """验证整型 dtype 不支持 requires_grad=True 时抛出异常。"""
    with pytest.raises(RuntimeError):
        npu_base_tensor.new_zeros(
            (2, 2), dtype=torch.int32, requires_grad=True, layout=torch.strided
        )
