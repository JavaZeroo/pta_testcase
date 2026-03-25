"""
测试目的：
1. 验证 Tensor.new_empty 在 NPU 上可正常调用、可返回 Tensor、返回对象位于 NPU。
2. 覆盖 size / dtype / device / requires_grad / layout / pin_memory 等入参维度的传参与不传参、正常与异常场景。
3. 补充 torch.Size 作为 size 入参、以及高维 shape 边界的接口覆盖。

API 名称：Tensor.new_empty

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| size | 已覆盖 | int / list / tuple / torch.Size，包含正常形状、空维度边界值、高维 shape、负维度异常、非法类型异常 |
| dtype | 已覆盖 | 默认不传、显式传 None、显式 float16、显式 int32、非法 dtype 类型异常 |
| device | 已覆盖 | 默认不传、显式传 None、显式 npu、非法 device 类型异常 |
| requires_grad | 已覆盖 | 默认不传、显式传 False、显式传 True、非 bool 类型异常，及 int dtype + requires_grad=True 异常 |
| layout | 已覆盖 | 显式传 torch.strided，及不支持 layout 的异常场景 |
| pin_memory | 已覆盖 | 显式传 False 正常返回；显式传 True 在 NPU 张量上应抛出异常；非 bool 类型异常 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值内容正确性 | new_empty 返回未初始化数据，测试聚焦接口与设备行为，不做数值比对 |
| 多 NPU 卡切换 | 当前用例仅验证单卡 NPU 上的基本功能覆盖，未强依赖多卡环境 |
"""

import pytest

import torch

try:
    import torch_npu  # noqa: F401
except ImportError:
    pytest.skip(
        "torch_npu 未安装，无法执行依赖 NPU 后端的 Tensor.new_empty 测试。",
        allow_module_level=True,
    )


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前 PyTorch 构建未注册 torch.npu 后端，无法创建 NPU Tensor 执行 Tensor.new_empty 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境已注册 torch.npu 后端，但当前无可用 NPU 设备，无法执行 Tensor.new_empty 测试。")


@pytest.fixture()
def npu_base_tensor():
    _require_npu()
    return torch.tensor([[1.0, 2.0], [3.0, 4.0]], device=torch.device("npu:0"))


@pytest.mark.parametrize("size", [(1,), [2, 3], 4, (0, 2)])
@pytest.mark.parametrize("dtype_arg", [None, torch.float16])
@pytest.mark.parametrize("device_arg", [None, torch.device("npu:0")])
@pytest.mark.parametrize("requires_grad", [False, True])
def test_tensor_new_empty_normal_cases(
    npu_base_tensor, size, dtype_arg, device_arg, requires_grad
):
    """验证正常输入下的调用、返回类型和 NPU 设备行为。"""
    assert callable(npu_base_tensor.new_empty)

    kwargs = {}
    if dtype_arg is not None:
        kwargs["dtype"] = dtype_arg
    if device_arg is not None:
        kwargs["device"] = device_arg
    if requires_grad:
        kwargs["requires_grad"] = True

    out = npu_base_tensor.new_empty(size, **kwargs)

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.device.index == 0
    assert out.shape == torch.Size(size if isinstance(size, (list, tuple)) else [size])
    assert out.requires_grad is requires_grad
    if dtype_arg is None:
        assert out.dtype == npu_base_tensor.dtype
    else:
        assert out.dtype == dtype_arg


def test_tensor_new_empty_explicit_int_dtype_on_npu(npu_base_tensor):
    """验证显式整型 dtype 的返回类型与 NPU 设备行为。"""
    out = npu_base_tensor.new_empty((2, 1), dtype=torch.int32, device=torch.device("npu:0"))

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.dtype == torch.int32
    assert out.requires_grad is False


def test_tensor_new_empty_explicit_none_dtype_and_device(npu_base_tensor):
    """验证显式传入 dtype=None 和 device=None 时继承基 tensor 的属性。"""
    out = npu_base_tensor.new_empty((2, 2), dtype=None, device=None)

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device == npu_base_tensor.device
    assert out.dtype == npu_base_tensor.dtype
    assert out.requires_grad is False


def test_tensor_new_empty_explicit_requires_grad_false(npu_base_tensor):
    """验证显式传入 requires_grad=False 时可正常返回且保持关闭梯度。"""
    out = npu_base_tensor.new_empty((2, 2), requires_grad=False)

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device == npu_base_tensor.device
    assert out.requires_grad is False


@pytest.mark.parametrize("bad_requires_grad", ["True", 1.5, object()])
def test_tensor_new_empty_invalid_requires_grad_type_raises(
    npu_base_tensor, bad_requires_grad
):
    """验证 requires_grad 传入非 bool 类型时通过 pytest.raises 抛出异常。"""
    with pytest.raises((TypeError, ValueError, RuntimeError)):
        npu_base_tensor.new_empty((2, 2), requires_grad=bad_requires_grad)


def test_tensor_new_empty_empty_shape_returns_scalar_tensor(npu_base_tensor):
    """验证 size=() 时返回 0 维 Tensor。"""
    out = npu_base_tensor.new_empty(())

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == torch.Size([])


@pytest.mark.parametrize(
    "bad_size, expected_exc",
    [
        ((-1,), RuntimeError),
        ((1, -2), RuntimeError),
        ("abc", TypeError),
        ((1, "x"), TypeError),
    ],
)
def test_tensor_new_empty_invalid_size_raises(npu_base_tensor, bad_size, expected_exc):
    """验证 size 非法时通过 pytest.raises 抛出异常。"""
    with pytest.raises(expected_exc):
        npu_base_tensor.new_empty(bad_size)


def test_tensor_new_empty_invalid_dtype_type_raises(npu_base_tensor):
    """验证非法 dtype 类型时通过 pytest.raises 抛出异常。"""
    with pytest.raises((TypeError, ValueError, RuntimeError)):
        npu_base_tensor.new_empty((2, 2), dtype="float32")


def test_tensor_new_empty_invalid_device_type_raises(npu_base_tensor):
    """验证非法 device 类型时通过 pytest.raises 抛出异常。"""
    with pytest.raises((TypeError, ValueError, RuntimeError, AssertionError)):
        npu_base_tensor.new_empty((2, 2), device="invalid_device")


def test_tensor_new_empty_requires_grad_with_int_dtype_raises(npu_base_tensor):
    """验证整型 dtype 不支持 requires_grad=True 时抛出异常。"""
    with pytest.raises(RuntimeError):
        npu_base_tensor.new_empty((2, 2), dtype=torch.int32, requires_grad=True)


def test_tensor_new_empty_explicit_layout_strided(npu_base_tensor):
    """验证显式传入默认 layout=torch.strided 时可正常返回 NPU Tensor。"""
    out = npu_base_tensor.new_empty((2, 3), layout=torch.strided)

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.layout == torch.strided
    assert out.shape == torch.Size([2, 3])


def test_tensor_new_empty_unsupported_layout_raises(npu_base_tensor):
    """验证传入不支持的 layout 时通过 pytest.raises 抛出异常。"""
    with pytest.raises((RuntimeError, TypeError, ValueError, NotImplementedError)):
        npu_base_tensor.new_empty((2, 3), layout=torch._mkldnn)


def test_tensor_new_empty_explicit_pin_memory_false(npu_base_tensor):
    """验证显式传入 pin_memory=False 时可正常返回 NPU Tensor。"""
    out = npu_base_tensor.new_empty((2, 3), pin_memory=False)

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == torch.Size([2, 3])


@pytest.mark.parametrize("bad_pin_memory", ["False", 1.5, object()])
def test_tensor_new_empty_invalid_pin_memory_type_raises(
    npu_base_tensor, bad_pin_memory
):
    """验证 pin_memory 传入非 bool 类型时通过 pytest.raises 抛出异常。"""
    with pytest.raises((TypeError, ValueError, RuntimeError)):
        npu_base_tensor.new_empty((2, 3), pin_memory=bad_pin_memory)


def test_tensor_new_empty_pin_memory_true_raises_on_npu(npu_base_tensor):
    """验证 NPU Tensor 传入 pin_memory=True 时会触发后端限制异常。"""
    with pytest.raises((RuntimeError, TypeError, ValueError)):
        npu_base_tensor.new_empty((2, 3), pin_memory=True)


def test_tensor_new_empty_accepts_torch_size_as_size(npu_base_tensor):
    """验证 size 支持 torch.Size 类型入参。"""
    size = torch.Size([2, 3])
    out = npu_base_tensor.new_empty(size)

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == size


def test_tensor_new_empty_high_dim_size_on_npu(npu_base_tensor):
    """验证高维 shape 入参在 NPU 上可正常创建张量。"""
    out = npu_base_tensor.new_empty((2, 1, 3, 1))

    assert out is not None
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == torch.Size([2, 1, 3, 1])
