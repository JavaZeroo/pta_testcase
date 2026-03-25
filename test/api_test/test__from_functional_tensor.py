"""
测试目的：
1. 验证 torch._from_functional_tensor 在 NPU 环境下可正常使用。
2. 验证 round-trip（torch._to_functional_tensor -> torch._from_functional_tensor）过程中，functional wrapper 保持基本属性（device/shape/dtype），且最终返回 Tensor 的 device/shape/dtype/requires_grad 与原始 Tensor 保持一致。
3. 验证非 functional tensor、非 Tensor 入参以及缺参场景下的异常行为。
4. 验证多个典型 dtype、shape 和 requires_grad 组合的覆盖情况。

API 名称：torch._from_functional_tensor

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| t（functional tensor） | 已覆盖 | 通过 torch._to_functional_tensor 构造后再调用 torch._from_functional_tensor |
| t（普通 NPU Tensor） | 已覆盖 | 传入非 functional tensor，验证异常行为 |
| t（非 Tensor） | 已覆盖 | 传入 None / int / list，验证类型错误 |
| 传参 / 缺参 | 已覆盖 | 正常传参与缺参 TypeError 均覆盖 |
| dtype | 已覆盖 | 默认不传 dtype，以及显式 float16 / float32 / int32 / int64 / bool / float64 |
| shape | 已覆盖 | 标量、1 维、2 维形状覆盖 |
| requires_grad | 已覆盖 | 覆盖 True / False 两种场景 |
| device | 已覆盖 | NPU 设备覆盖 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值正确性校验 | 已在正常 round-trip 场景补充验证返回结果与原始 Tensor 数据一致 |
| 多 NPU 卡切换 | 当前用例聚焦单卡 NPU 的基础功能，未依赖多卡环境 |
| CPU / CUDA 路径 | 本测试文件目标是 NPU 功能验证，未覆盖其他设备路径 |
| 复合输入类型 | API 签名仅接受单个 Tensor 参数，不存在复合输入类型场景 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu_functional_apis():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch._from_functional_tensor 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch._from_functional_tensor 测试。")
    if not hasattr(torch, "_sync"):
        pytest.skip("当前 PyTorch 版本缺少 torch._sync，无法正确同步 functional tensor 状态。")
    if not hasattr(torch, "_to_functional_tensor"):
        pytest.skip("当前 PyTorch 版本缺少 torch._to_functional_tensor，无法构造 functional tensor。")
    if not hasattr(torch, "_from_functional_tensor"):
        pytest.skip("当前 PyTorch 版本缺少 torch._from_functional_tensor，无法验证功能。")


def _make_npu_tensor(shape, dtype=None):
    if dtype is None:
        return torch.ones(shape, device=torch.device("npu:0"))
    return torch.ones(shape, device=torch.device("npu:0"), dtype=dtype)


def _to_functional_npu_tensor(tensor):
    functional_tensor = torch._to_functional_tensor(tensor)
    torch._sync(functional_tensor)
    return functional_tensor


@pytest.fixture(scope="module")
def npu_device():
    _require_npu_functional_apis()
    return torch.device("npu:0")


@pytest.mark.parametrize(
    "shape,dtype,requires_grad",
    [
        ((), None, False),
        ((), torch.float16, False),
        ((), torch.float16, True),
        ((1,), torch.float32, False),
        ((1,), torch.float32, True),
        ((2, 3), torch.float64, False),
        ((2, 3), torch.float64, True),
        ((2, 3), torch.int32, False),
        ((1,), torch.int64, False),
        ((), torch.bool, False),
    ],
)
def test_from_functional_tensor_round_trip_preserves_tensor_properties(npu_device, shape, dtype, requires_grad):
    """验证 functional tensor round-trip 后的类型、设备、形状、dtype 和 requires_grad 保持一致。"""
    base_tensor = _make_npu_tensor(shape, dtype=dtype).requires_grad_(requires_grad)
    functional_tensor = _to_functional_npu_tensor(base_tensor)

    assert isinstance(functional_tensor, torch.Tensor)
    assert functional_tensor.device.type == "npu"
    assert functional_tensor.device.index == 0
    assert functional_tensor.shape == base_tensor.shape
    assert functional_tensor.dtype == base_tensor.dtype
    # Functionalization does not propagate requires_grad to the wrapper
    assert functional_tensor.requires_grad is False

    out = torch._from_functional_tensor(functional_tensor)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.device.index == 0
    assert out.shape == base_tensor.shape
    assert out.dtype == base_tensor.dtype
    assert out.requires_grad == base_tensor.requires_grad
    assert torch.equal(out, base_tensor)


def test_from_functional_tensor_round_trip_works_for_scalar_shape(npu_device):
    """验证标量 Tensor 的 round-trip 仍保持 NPU Tensor 属性。"""
    base_tensor = _make_npu_tensor((), dtype=torch.float32)
    functional_tensor = _to_functional_npu_tensor(base_tensor)

    out = torch._from_functional_tensor(functional_tensor)

    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
    assert out.shape == torch.Size([])
    assert out.dtype == torch.float32
    assert out.requires_grad is False
    assert torch.equal(out, base_tensor)


def test_from_functional_tensor_non_functional_npu_tensor_raises(npu_device):
    """验证普通 NPU Tensor 不是 functional tensor 时会抛出异常。"""
    base_tensor = _make_npu_tensor((2, 3), dtype=torch.float32).requires_grad_(True)

    with pytest.raises(RuntimeError):
        torch._from_functional_tensor(base_tensor)


@pytest.mark.parametrize("bad_input", [None, 1, [1, 2, 3], "abc"])
def test_from_functional_tensor_non_tensor_input_raises_type_error(npu_device, bad_input):
    """验证非 Tensor 入参会抛出 TypeError。"""
    with pytest.raises(TypeError):
        torch._from_functional_tensor(bad_input)


def test_from_functional_tensor_missing_argument_raises_type_error(npu_device):
    """验证缺参时会抛出 TypeError。"""
    with pytest.raises(TypeError):
        torch._from_functional_tensor()
