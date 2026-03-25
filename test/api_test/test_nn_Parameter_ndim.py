"""
测试目的：
1. 验证 torch.nn.Parameter.ndim 在 NPU 上可正常读取，且返回值类型为 int。
2. 覆盖不同维度 Parameter 的 ndim 行为，确认 ndim 与 shape 维度数一致。
3. 覆盖 NPU 设备创建，确保测试对象实际生成于 NPU。

API 名称：torch.nn.Parameter.ndim

覆盖的参数维度表：
| 维度/场景 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 标量 Parameter | 已覆盖 | shape=()，ndim=0 |
| 1D Parameter | 已覆盖 | shape=(n,) |
| 2D Parameter | 已覆盖 | shape=(n, m) |
| 3D Parameter | 已覆盖 | shape=(n, m, k) |
| 4D Parameter | 已覆盖 | shape=(n, m, k, p) |
| 零元素 Parameter | 已覆盖 | shape=(0,) 与 shape=(0, 3)，验证空数据下维度属性仍可读取 |
| NPU 设备 | 已覆盖 | Parameter 在 npu 设备上创建并读取 ndim |
| 返回值类型 | 已覆盖 | 验证 ndim 为 int |
| API 入参 None/非None、传/不传 | 不适用 | 该 API 为无参属性访问，没有可传入参数 |
| 主要枚举 | 不适用 | 该 API 不涉及枚举入参 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| ndim 的内部实现细节 | 仅验证公开属性行为，不检查底层实现 |
| 多卡/分布式场景 | 当前用例仅覆盖单卡 NPU 上的基础行为 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.nn.Parameter.ndim 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.nn.Parameter.ndim 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device(f"npu:{torch.npu.current_device()}")


def _make_parameter(npu_device, shape):
    data = torch.ones(shape, device=npu_device)
    return torch.nn.Parameter(data)


@pytest.mark.parametrize(
    "shape, expected_ndim",
    [
        ((), 0),
        ((5,), 1),
        ((2, 3), 2),
        ((2, 3, 4), 3),
        ((1, 2, 3, 4), 4),
        ((0,), 1),
        ((0, 3), 2),
    ],
)
def test_parameter_ndim_matches_shape_and_type(npu_device, shape, expected_ndim):
    """验证不同维度的 NPU Parameter 读取 ndim 时返回 int 且与 shape 维度数一致。"""
    param = _make_parameter(npu_device, shape)

    assert param.device.type == "npu"
    assert param.device.index == torch.npu.current_device()
    assert isinstance(param.ndim, int)
    assert param.ndim == expected_ndim
    assert param.ndim == len(param.shape)
