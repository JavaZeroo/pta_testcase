"""
测试目的：
1. 验证 torch._sync 在 NPU 场景下可以正常调用，并覆盖普通 Tensor 与 functional tensor 两类主要输入。
2. 覆盖参数传入/不传入、None/非 None、主要类型、主要 dtype、主要 shape 以及正常/异常场景。
3. 针对内部 API 仅做可调用性、返回值、设备与形状等行为验证，不做具体数值精度校验。

API 名称：torch._sync

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 参数个数 | 已覆盖 | 传入 1 个参数的正常场景、无参数异常场景 |
| 参数类型 | 已覆盖 | NPU 普通 Tensor、functional tensor、None、int、str、list |
| None / 非 None | 已覆盖 | 覆盖 None 和非 None 入参 |
| 主要枚举值 | 不适用 | 该 API 无枚举参数 |
| 主要 dtype | 已覆盖 | float32 / int64 / bool |
| 主要 shape | 已覆盖 | 1D / 2D / 标量 / 空 Tensor |
| device | 已覆盖 | NPU:0 |
| 正常 / 异常 | 已覆盖 | 正常调用返回 None；异常入参使用 pytest.raises |
| functional tensor | 已覆盖 | 通过 torch._to_functional_tensor 构造后调用 torch._sync |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 多 NPU 卡切换 | 当前用例仅验证单卡 NPU 基本行为，不依赖多卡拓扑 |
| 具体内部同步状态变化 | torch._sync 为内部函数，外部无法直接观测底层同步状态，仅能通过可调用性、返回值和张量形态间接验证 |
| 数值正确性细节 | 按要求不做具体数值正确性校验，仅验证接口行为 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch._sync 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch._sync 测试。")


def _require_sync_api():
    if not hasattr(torch, "_sync"):
        pytest.skip("当前 PyTorch 版本不存在 torch._sync，跳过内部 API 测试。")
    if not callable(torch._sync):
        pytest.skip("当前 PyTorch 版本的 torch._sync 不是可调用对象，无法测试。")
    if not hasattr(torch, "_to_functional_tensor"):
        pytest.skip("当前 PyTorch 版本缺少 torch._to_functional_tensor，无法构造 functional tensor。")
    if not hasattr(torch, "_from_functional_tensor"):
        pytest.skip("当前 PyTorch 版本缺少 torch._from_functional_tensor，无法验证同步结果。")


@pytest.fixture(scope="module")
def npu_device():
    _require_npu()
    return torch.device("npu:0")


def _make_base_tensor(device, case_name):
    if case_name == "float32_1d":
        return torch.tensor([1.25, -3.5, 0.0], dtype=torch.float32, device=device)
    if case_name == "int64_2d":
        return torch.tensor([[1, 2], [3, 4]], dtype=torch.int64, device=device)
    if case_name == "bool_scalar":
        return torch.tensor(True, dtype=torch.bool, device=device)
    if case_name == "float32_empty":
        return torch.empty((0,), dtype=torch.float32, device=device)
    raise AssertionError(f"未知测试用例: {case_name}")


def _to_functional_npu_tensor(base_tensor):
    _require_sync_api()
    if not hasattr(torch, "_to_functional_tensor"):
        pytest.skip("当前 PyTorch 版本缺少 torch._to_functional_tensor，无法构造 functional tensor。")
    try:
        functional_tensor = torch._to_functional_tensor(base_tensor)
    except RuntimeError as exc:
        error_message = str(exc).lower()
        unsupported_keywords = ("not support", "unsupported", "not implemented", "unavailable")
        if any(keyword in error_message for keyword in unsupported_keywords):
            pytest.skip(f"当前 NPU 后端不支持将 Tensor 转为 functional tensor，原因：{exc}")
        raise

    if hasattr(torch, "_is_functional_tensor"):
        assert torch._is_functional_tensor(functional_tensor)
    return functional_tensor


@pytest.mark.parametrize(
    "case_name",
    [
        "float32_1d",
        "int64_2d",
        "bool_scalar",
        "float32_empty",
    ],
)
def test_torch_sync_functional_tensor_normal_cases_on_npu(npu_device, case_name):
    """验证不同 dtype/shape 的 NPU functional tensor 调用 torch._sync 可正常返回。"""
    _require_sync_api()

    base_tensor = _make_base_tensor(npu_device, case_name)
    assert isinstance(base_tensor, torch.Tensor)
    assert base_tensor.device.type == "npu"
    assert base_tensor.device.index == 0

    test_tensor = _to_functional_npu_tensor(base_tensor)

    result = torch._sync(test_tensor)

    assert result is None
    assert isinstance(test_tensor, torch.Tensor)
    assert test_tensor.device.type == "npu"
    assert test_tensor.device.index == 0
    synced_tensor = torch._from_functional_tensor(test_tensor)
    assert isinstance(synced_tensor, torch.Tensor)
    assert synced_tensor.device.type == "npu"
    assert synced_tensor.device.index == 0
    assert synced_tensor.shape == base_tensor.shape
    assert synced_tensor.dtype == base_tensor.dtype


@pytest.mark.parametrize("case_name", ["float32_1d", "int64_2d", "bool_scalar", "float32_empty"])
def test_torch_sync_regular_tensor_raises_runtime_error(npu_device, case_name):
    """验证普通 NPU Tensor 传给 torch._sync 时会抛出 RuntimeError。"""
    _require_sync_api()

    base_tensor = _make_base_tensor(npu_device, case_name)

    with pytest.raises(RuntimeError):
        torch._sync(base_tensor)


def test_torch_sync_functional_tensor_makes_pending_view_mutation_observable(npu_device):
    """验证 functional tensor 的待同步 view mutation 在调用 torch._sync 后可被观察到。"""
    _require_sync_api()

    base_tensor = torch.arange(4, dtype=torch.float32, device=npu_device)
    functional_tensor = _to_functional_npu_tensor(base_tensor)
    mutated_view = functional_tensor.view(2, 2)
    stale_view = functional_tensor.view(2, 2)
    delta = torch.ones((2, 2), dtype=torch.float32, device=npu_device)
    expected_before_sync = torch.tensor([[0.0, 1.0], [2.0, 3.0]], dtype=torch.float32, device=npu_device)
    expected_after_sync = expected_before_sync + delta

    mutated_view.add_(delta)

    before_sync = torch._from_functional_tensor(stale_view)
    assert torch.equal(before_sync, expected_before_sync)

    result = torch._sync(stale_view)

    assert result is None
    after_sync = torch._from_functional_tensor(stale_view)
    assert torch.equal(after_sync, expected_after_sync)


def test_torch_sync_no_arguments_raises():
    """验证 torch._sync 无参数调用时抛出异常。"""
    _require_sync_api()

    with pytest.raises(TypeError):
        torch._sync()


@pytest.mark.parametrize("bad_arg", [None, 123, "abc", [1, 2, 3]])
def test_torch_sync_non_tensor_argument_raises(bad_arg):
    """验证 torch._sync 传入非 Tensor 参数时抛出异常。"""
    _require_sync_api()

    with pytest.raises(TypeError):
        torch._sync(bad_arg)
