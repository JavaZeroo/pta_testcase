"""
测试目的：
1. 验证 torch.Event 在 NPU 环境下可正常创建、记录、等待、同步、查询与计时。
2. 覆盖构造参数 device / enable_timing 的传参、不传参、None/非 None、主要类型与主要枚举值。
3. 覆盖正常/异常场景，并在 NPU 后端不支持 elapsed_time 时按要求运行时跳过。

API 名称：torch.Event

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| device | 已覆盖 | 不传；传 torch.device("npu:0")；传字符串 "npu"/"npu:0"；非法 device 值/类型异常 |
| enable_timing | 已覆盖 | 不传（默认 False）；显式 False/True；非法类型异常 |
| record(stream) | 已覆盖 | 传入 stream 与不传 stream 两种场景 |
| wait(stream) | 已覆盖 | 传入 stream 与不传 stream 两种场景 |
| query() | 已覆盖 | 记录前、记录后、同步后均覆盖返回 bool |
| synchronize() | 已覆盖 | 正常调用覆盖 |
| elapsed_time(end_event) | 条件覆盖 | 仅在 enable_timing=True 时调用；若后端不支持则运行时跳过 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| elapsed_time 的具体数值正确性 | 本测试聚焦接口可用性、返回类型与 NPU 事件链路，不校验计时精确值 |
| 多 NPU 卡场景 | 当前用例以单卡 NPU 为主，未依赖多卡拓扑 |
| 事件跨进程/跨设备同步语义 | 该行为与运行环境和调度强相关，超出本文件的基础功能覆盖范围 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu_event_api():
    if not hasattr(torch, "Event"):
        pytest.skip("当前 PyTorch 版本未暴露 torch.Event，跳过本次 NPU 功能测试。")
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.Event 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.Event 测试。")


@pytest.fixture()
def npu_device():
    _require_npu_event_api()
    return torch.device("npu:0")


@pytest.fixture()
def event_cls():
    _require_npu_event_api()
    return torch.Event


def _make_event(event_cls, device=None, enable_timing=None):
    kwargs = {}
    if device is not None:
        kwargs["device"] = device
    if enable_timing is not None:
        kwargs["enable_timing"] = enable_timing
    return event_cls(**kwargs)


def _assert_event_on_npu(event):
    assert hasattr(event, "device")
    assert isinstance(event.device, torch.device)
    assert event.device.type == "npu"


def _require_elapsed_time_supported(event_cls, npu_device):
    """探测当前 NPU 后端是否支持 Event.elapsed_time。"""
    probe_start = event_cls(device="npu:0", enable_timing=True)
    probe_end = event_cls(device="npu:0", enable_timing=True)
    stream = torch.npu.Stream(device=npu_device)
    probe_start.record(stream)
    probe_end.record(stream)
    probe_start.synchronize()
    probe_end.synchronize()
    try:
        probe_start.elapsed_time(probe_end)
    except (RuntimeError, NotImplementedError) as exc:
        if "Backend doesn't support elapsedTime" in str(exc):
            pytest.skip("当前 NPU 后端不支持 Event.elapsed_time，跳过相关用例。")
        raise


def test_torch_event_constructor_and_basic_lifecycle_on_npu(event_cls, npu_device):
    """验证构造参数传/不传、None/非None，以及基本事件链路。"""
    # 不传 device / enable_timing 时，在 NPU 设备上下文中创建，避免形成伪覆盖。
    with torch.npu.device(npu_device):
        default_event = _make_event(event_cls)
    assert isinstance(default_event, event_cls)
    _assert_event_on_npu(default_event)

    # 未记录事件时 query 应直接完成。
    assert default_event.query() is True

    # 传 torch.device 类型和显式 enable_timing=False。
    device_event = _make_event(event_cls, device=torch.device("npu:0"), enable_timing=False)
    assert isinstance(device_event, event_cls)
    _assert_event_on_npu(device_event)

    # 传字符串类型和显式 enable_timing=True。
    timing_event = _make_event(event_cls, device="npu", enable_timing=True)
    assert isinstance(timing_event, event_cls)
    _assert_event_on_npu(timing_event)

    query_stream = torch.npu.Stream(device=npu_device)
    with torch.npu.stream(query_stream):
        _ = torch.ones(1024 * 1024, device=npu_device) + 1
        timing_event.record()

    # 已记录且所在流仍有待完成工作时，query 应体现未完成状态；同步后转为完成。
    assert timing_event.query() is False
    timing_event.synchronize()
    assert timing_event.query() is True

    # 覆盖 synchronize 的基础调用。
    default_event.synchronize()
    device_event.synchronize()


def test_torch_event_record_and_wait_have_observable_stream_semantics(event_cls, npu_device):
    """验证 record/wait 不仅可调用，还能在跨流场景中建立可观测的顺序语义。"""
    record_stream = torch.npu.Stream(device=npu_device)
    wait_stream = torch.npu.Stream(device=npu_device)
    explicit_event = _make_event(event_cls, device="npu:0")
    default_event = _make_event(event_cls, device="npu:0")

    x_explicit = torch.zeros(256, device=npu_device)
    with torch.npu.stream(record_stream):
        x_explicit.add_(1)
    explicit_event.record(record_stream)
    explicit_event.wait(wait_stream)
    with torch.npu.stream(wait_stream):
        y_explicit = x_explicit + 1
    wait_stream.synchronize()
    assert torch.equal(y_explicit.cpu(), torch.full((256,), 2.0))

    x_default = torch.zeros(256, device=npu_device)
    with torch.npu.stream(record_stream):
        x_default.add_(1)
        default_event.record()
    with torch.npu.stream(wait_stream):
        default_event.wait()
        y_default = x_default + 1
    wait_stream.synchronize()
    assert torch.equal(y_default.cpu(), torch.full((256,), 2.0))


@pytest.mark.parametrize("device_arg", [None, "npu", "npu:0"])
def test_torch_event_elapsed_time_when_enable_timing(event_cls, npu_device, device_arg):
    """验证 enable_timing=True 时可调用 elapsed_time，并返回数值类型。"""
    _require_elapsed_time_supported(event_cls, npu_device)

    start_event = _make_event(event_cls, device=device_arg, enable_timing=True)
    end_event = _make_event(event_cls, device=device_arg, enable_timing=True)

    assert isinstance(start_event, event_cls)
    assert isinstance(end_event, event_cls)

    stream = torch.npu.Stream(device=npu_device)
    start_event.record(stream)
    end_event.record(stream)
    start_event.synchronize()
    end_event.synchronize()

    elapsed = start_event.elapsed_time(end_event)
    assert isinstance(elapsed, float)


def test_torch_event_invalid_device_raises(event_cls):
    """验证非法 device 值/类型会通过 pytest.raises 抛出异常。"""
    with pytest.raises((TypeError, ValueError, RuntimeError)):
        event_cls(device="invalid_device", enable_timing=False)
    with pytest.raises((TypeError, ValueError, RuntimeError)):
        event_cls(device=object(), enable_timing=True)


def test_torch_event_invalid_enable_timing_type_raises(event_cls):
    """验证 enable_timing 传入非 bool 类型时会抛出异常。"""
    with pytest.raises((TypeError, ValueError, RuntimeError)):
        event_cls(device="npu:0", enable_timing="invalid")


def test_torch_event_invalid_method_arguments_raise(event_cls):
    """验证 record/wait/query 的方法级异常参数场景。"""
    event = _make_event(event_cls, device="npu:0")

    with pytest.raises((TypeError, RuntimeError, ValueError)):
        event.record("invalid_stream")
    with pytest.raises((TypeError, RuntimeError, ValueError)):
        event.wait("invalid_stream")
    with pytest.raises(TypeError):
        event.query("unexpected_arg")


def test_torch_event_elapsed_time_without_enable_timing_raises(event_cls, npu_device):
    """验证未启用 timing 时调用 elapsed_time 会抛出异常。"""
    _require_elapsed_time_supported(event_cls, npu_device)

    start_event = _make_event(event_cls, device="npu:0", enable_timing=False)
    end_event = _make_event(event_cls, device="npu:0", enable_timing=True)

    stream = torch.npu.Stream(device=npu_device)
    start_event.record(stream)
    end_event.record(stream)
    start_event.synchronize()
    end_event.synchronize()

    with pytest.raises(RuntimeError):
        start_event.elapsed_time(end_event)
