"""
测试目的：
1. 验证 torch.nn.Parameter.itemsize 在 NPU 上可正常访问，返回值类型为 int，且与 element_size() 保持一致。
2. 覆盖 Parameter 构造时的主要参数维度：data 传/不传、requires_grad 传/不传、requires_grad=None 异常、主要 dtype、主要形状边界。
3. 覆盖 itemsize 只读属性的正常访问与写入异常场景，确保接口行为稳定。

API 名称：torch.nn.Parameter.itemsize

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| itemsize 访问方式（无入参） | 已覆盖 | 直接访问 itemsize 属性 |
| Parameter 设备 | 已覆盖 | 通过 NPU 上创建/持有的 Parameter 验证 |
| data 传入 | 已覆盖 | 使用 NPU Tensor 作为 data 构造 Parameter |
| data 不传 | 未覆盖 | `Parameter(None)` 会构造 CPU 空参数，不满足本用例“所有测试必须在 NPU 上运行”的约束 |
| requires_grad 传入 | 已覆盖 | 覆盖 True / False 两种显式传参 |
| requires_grad 不传 | 已覆盖 | 覆盖默认值路径 |
| requires_grad=None | 已覆盖 | 验证构造阶段抛出异常 |
| dtype=float32 | 已覆盖 | 主要浮点类型 |
| dtype=float64 | 已覆盖 | 主要浮点类型 |
| dtype=float16 | 已覆盖 | 主要浮点类型 |
| dtype=complex64 | 已覆盖 | 主要复数类型 |
| dtype=complex128 | 已覆盖 | 主要复数类型 |
| dtype=int32 | 已覆盖 | 主要整型类型 |
| dtype=int64 | 已覆盖 | 主要整型类型 |
| dtype=int8 | 已覆盖 | 边界小整数类型 |
| dtype=bool | 已覆盖 | 主要布尔类型 |
| shape=标量 | 已覆盖 | 覆盖 0 维边界 |
| shape=空张量 | 已覆盖 | 覆盖 0 元素边界 |
| shape=多维张量 | 已覆盖 | 覆盖常规多维场景 |
| itemsize 可写 | 已覆盖异常 | 验证只读属性写入会抛出 AttributeError |
| 具体 itemsize 数值 | 已覆盖 | 对主要 dtype 断言明确字节数 |
| 多卡/跨卡场景 | 未覆盖 | 当前用例仅验证单卡 NPU 上的基础属性行为 |
| 训练/反向传播链路 | 未覆盖 | itemsize 为纯属性读取，本文件不扩展到训练流程 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.nn.Parameter.itemsize 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.nn.Parameter.itemsize 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device(f"npu:{torch.npu.current_device()}")


def _make_npu_tensor(npu_device, dtype, shape):
    numel = 1
    for dim in shape:
        numel *= dim
    if numel == 0:
        return torch.empty(shape, dtype=dtype, device=npu_device)
    if dtype in (torch.complex64, torch.complex128):
        return torch.tensor([1 + 0j] * numel, dtype=dtype, device=npu_device).reshape(shape)
    return torch.ones(shape, dtype=dtype, device=npu_device)


@pytest.mark.parametrize(
    "dtype, shape, use_default_requires_grad, requires_grad, expected_itemsize",
    [
        (torch.float32, (2, 2), True, None, 4),
        (torch.float64, (), False, True, 8),
        (torch.float16, (0,), False, False, 2),
        (torch.complex64, (2,), False, True, 8),
        (torch.complex128, (1, 2), False, True, 16),
        (torch.int32, (2, 1), False, False, 4),
        (torch.int64, (1,), False, False, 8),
        (torch.int8, (3,), False, False, 1),
        (torch.bool, (4,), False, False, 1),
    ],
)
def test_parameter_itemsize_on_npu_and_matches_element_size(
    npu_device, dtype, shape, use_default_requires_grad, requires_grad, expected_itemsize
):
    """验证 NPU 上不同 dtype、形状、requires_grad 组合下的 Parameter.itemsize。"""
    data = _make_npu_tensor(npu_device, dtype, shape)

    if use_default_requires_grad:
        param = torch.nn.Parameter(data)
    else:
        param = torch.nn.Parameter(data, requires_grad=requires_grad)

    assert isinstance(param, torch.nn.Parameter)
    assert param.device.type == "npu"
    if use_default_requires_grad:
        assert param.requires_grad is True
    else:
        assert param.requires_grad is requires_grad

    itemsize = param.itemsize
    assert isinstance(itemsize, int)
    assert itemsize == expected_itemsize
    assert itemsize == param.element_size()


def test_parameter_itemsize_is_int_for_npu_parameter(npu_device):
    """验证 NPU 上 Parameter.itemsize 返回值的类型为 int。"""
    param = torch.nn.Parameter(
        torch.tensor([1.0, 2.0], dtype=torch.float32, device=npu_device)
    )

    assert param.device.type == "npu"
    assert isinstance(param.itemsize, int)
    assert param.itemsize == 4
    assert param.itemsize == param.element_size()


def test_parameter_itemsize_is_read_only_on_npu(npu_device):
    """验证 NPU 上 itemsize 作为只读属性，写入时会抛出异常。"""
    param = torch.nn.Parameter(
        torch.tensor([1.0, 2.0], dtype=torch.float32, device=npu_device)
    )

    with pytest.raises(AttributeError):
        param.itemsize = 4


def test_parameter_requires_grad_none_raises_on_npu(npu_device):
    """验证 requires_grad=None 时，Parameter 构造阶段会抛出异常。"""
    with pytest.raises(TypeError):
        torch.nn.Parameter(
            torch.tensor([1.0, 2.0], dtype=torch.float32, device=npu_device),
            requires_grad=None,
        )
