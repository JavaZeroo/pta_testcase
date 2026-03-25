"""
测试目的：
1. 验证 torch.nn.Parameter.size 在 NPU 上可正常调用，且返回类型与 PyTorch 约定一致。
2. 覆盖 size() / size(None) / size(dim) 三类调用方式，确认参数传入与不传入的行为。
3. 覆盖合法 dim、越界 dim、非法类型 dim 等正常/异常场景，确保 NPU 后端行为稳定。
4. 覆盖标量、1D、2D、3D 等不同形状的 Parameter，仅校验元数据，不做具体数值正确性校验。

API 名称：torch.nn.Parameter.size

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 是否传入 dim | 已覆盖 | 不传入、显式传 None、传入合法 dim、传入越界 dim、传入非法类型 |
| dim 取值 | 已覆盖 | 正维度、负维度、越界维度、命名维度字符串 |
| dim 类型 | 已覆盖 | int、str、None、float（异常） |
| 返回类型 | 已覆盖 | 无 dim/传 None 时返回 torch.Size，有合法 dim 时返回 int |
| 参数形状 | 已覆盖 | 标量、1D、2D、3D Parameter |
| 运行设备 | 已覆盖 | Parameter 创建与调用均在 NPU 上执行 |
| 异常场景 | 已覆盖 | 越界 dim 抛出 IndexError，非法类型 dim 抛出 TypeError |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 多 NPU / 分布式场景 | 当前仅验证单卡 NPU 的基础接口功能，不依赖多卡环境 |
| 具体数值计算正确性 | size 仅返回形状元数据，不涉及数值计算，因此不做数值校验 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.nn.Parameter.size 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.nn.Parameter.size 测试。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device(f"npu:{torch.npu.current_device()}")


def _make_parameter(npu_device, shape):
    if shape == ():
        data = torch.tensor(1.0, device=npu_device)
    else:
        data = torch.ones(shape, device=npu_device)
    return torch.nn.Parameter(data)


@pytest.mark.parametrize("shape", [(), (5,), (2, 3), (2, 3, 4)])
def test_parameter_size_without_dim_and_with_none_returns_torch_size(npu_device, shape):
    """验证 size() 与 size(None) 均返回 torch.Size，且与 Parameter.shape 一致。"""
    param = _make_parameter(npu_device, shape)

    out_no_arg = param.size()
    out_none = param.size(None)

    assert param.device.type == "npu"
    assert isinstance(out_no_arg, torch.Size)
    assert isinstance(out_none, torch.Size)
    assert out_no_arg == param.shape
    assert out_none == param.shape


@pytest.mark.parametrize(
    "shape, dim, expected_dim_index",
    [
        ((), 0, None),
        ((), -1, None),
        ((5,), 0, 0),
        ((5,), -1, -1),
        ((2, 3), 0, 0),
        ((2, 3), 1, 1),
        ((2, 3), -1, -1),
        ((2, 3, 4), 0, 0),
        ((2, 3, 4), 1, 1),
        ((2, 3, 4), 2, 2),
        ((2, 3, 4), -1, -1),
    ],
)
def test_parameter_size_with_dim_returns_int_and_matches_shape(npu_device, shape, dim, expected_dim_index):
    """验证传入合法 dim 时返回 int；对标量场景，越界 dim 应触发异常。"""
    param = _make_parameter(npu_device, shape)

    if expected_dim_index is None:
        with pytest.raises(IndexError):
            param.size(dim)
        return

    out = param.size(dim)

    assert param.device.type == "npu"
    assert isinstance(out, int)
    assert out == param.shape[expected_dim_index]


def test_parameter_size_with_named_dim_string_returns_int(npu_device):
    """验证命名维度字符串可作为 dim 传入，并返回对应维度长度。"""
    param = torch.nn.Parameter(torch.ones((2, 3, 4), device=npu_device, names=("N", "C", "W")))

    out = param.size("C")

    assert param.device.type == "npu"
    assert isinstance(out, int)
    assert out == 3


@pytest.mark.parametrize(
    "shape, dim",
    [
        ((), 1),
        ((), -2),
        ((5,), 1),
        ((5,), -2),
        ((2, 3), 2),
        ((2, 3), -3),
        ((2, 3, 4), 3),
        ((2, 3, 4), -4),
    ],
)
def test_parameter_size_out_of_range_dim_raises_index_error(npu_device, shape, dim):
    """验证越界 dim 调用 size 时抛出 IndexError。"""
    param = _make_parameter(npu_device, shape)

    with pytest.raises(IndexError):
        param.size(dim)


@pytest.mark.parametrize("invalid_dim", [1.5, 0.0, object()])
def test_parameter_size_invalid_type_raises_type_error(npu_device, invalid_dim):
    """验证非法类型 dim 调用 size 时抛出 TypeError。"""
    param = _make_parameter(npu_device, (2, 3))

    with pytest.raises(TypeError):
        param.size(invalid_dim)
