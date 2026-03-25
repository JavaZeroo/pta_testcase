"""
测试目的：
1. 验证 torch._logging.warning_once 可被正常调用。
2. 验证 logger 对象、message 取 None/非 None、*args 传参与 **kwargs 传参、重复调用去重、不同参数组合不去重，以及异常场景。
3. 仅基于可观察行为验证 warning_once 的“同参数只告警一次”语义，不校验真实日志文本和底层缓存实现细节。

API 名称：torch._logging.warning_once(logger_obj, *args, **kwargs)

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| API 存在性 / callable | 已覆盖 | 检查 torch._logging.warning_once 是否存在且可调用，不存在则直接失败 |
| logger_obj 非 None | 已覆盖 | 传入可记录 warning 的 logger 对象 |
| logger_obj 为 None | 已覆盖 | 传入 None 触发 AttributeError |
| message 为非 None | 已覆盖 | 传入字符串、整数等可哈希消息 |
| message 为 None | 已覆盖 | 传入 None 作为消息参数 |
| 枚举型参数 | 不适用 | 该 API 无显式枚举入参 |
| *args 不传 / 传入 | 已覆盖 | 分别覆盖无 message 和格式化参数透传的调用场景 |
| **kwargs 不传 / 传入 | 已覆盖 | 覆盖无 kwargs 和传入 stacklevel 等可哈希 kwargs |
| 重复调用去重 | 已覆盖 | 相同 logger + 相同参数多次调用，仅触发一次 logger.warning |
| 不同参数组合 | 已覆盖 | 不同 message、不同 *args、不同 kwargs 会分别触发 logger.warning |
| 异常场景 | 已覆盖 | 覆盖 logger_obj=None、缺少 message、传入不可哈希 kwargs 等场景 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 真实日志后端的文本格式、颜色、时间戳等输出细节 | 本测试只验证 warning_once 的调用和去重行为，不校验日志展示格式 |
| warning_once 内部 lru_cache 的实现细节 | 仅验证外部可观察行为，避免与具体实现强耦合 |
"""

import logging

import pytest
import torch


def _get_warning_once():
    assert hasattr(torch, "_logging"), "当前环境缺少 torch._logging，无法测试 warning_once。"
    assert hasattr(torch._logging, "warning_once"), "当前环境缺少 torch._logging.warning_once。"
    warning_once = torch._logging.warning_once
    assert callable(warning_once), "torch._logging.warning_once 不可调用。"
    return warning_once


class _RecorderLogger:
    def __init__(self):
        self.calls = []

    def warning(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_warning_once_callable():
    """验证 API 存在且可调用。"""
    warning_once = _get_warning_once()
    assert callable(warning_once)


def test_warning_once_string_message_logs_once():
    """验证传入字符串消息时可正常记录，且重复调用只记录一次。"""
    warning_once = _get_warning_once()
    logger = _RecorderLogger()

    warning_once(logger, "warning only once")
    warning_once(logger, "warning only once")

    assert len(logger.calls) == 1
    assert logger.calls[0][0] == ("warning only once",)
    assert logger.calls[0][1] == {}


def test_warning_once_same_message_multiple_calls_only_warns_once():
    """验证相同消息重复调用时，仅触发一次 logger.warning。"""
    warning_once = _get_warning_once()
    logger = _RecorderLogger()

    warning_once(logger, "same message")
    warning_once(logger, "same message")

    assert len(logger.calls) == 1
    assert logger.calls[0][0] == ("same message",)


def test_warning_once_different_messages_warn_twice():
    """验证不同消息会分别触发 logger.warning。"""
    warning_once = _get_warning_once()
    logger = _RecorderLogger()

    warning_once(logger, "message-a")
    warning_once(logger, "message-b")

    assert len(logger.calls) == 2
    assert logger.calls[0][0] == ("message-a",)
    assert logger.calls[1][0] == ("message-b",)


@pytest.mark.parametrize("message", ["string-message", 123, None])
def test_warning_once_message_types_are_forwarded(message):
    """验证字符串、整数和 None 消息都会透传给 logger.warning。"""
    warning_once = _get_warning_once()
    logger = _RecorderLogger()

    warning_once(logger, message)

    assert len(logger.calls) == 1
    assert logger.calls[0][0] == (message,)


def test_warning_once_args_are_forwarded_and_part_of_cache_key():
    """验证 *args 可透传，且不同 *args 会被视为不同调用。"""
    warning_once = _get_warning_once()
    logger = _RecorderLogger()

    warning_once(logger, "value=%s", 1)
    warning_once(logger, "value=%s", 1)
    warning_once(logger, "value=%s", 2)

    assert len(logger.calls) == 2
    assert logger.calls[0][0] == ("value=%s", 1)
    assert logger.calls[0][1] == {}
    assert logger.calls[1][0] == ("value=%s", 2)
    assert logger.calls[1][1] == {}


def test_warning_once_kwargs_are_forwarded_and_part_of_cache_key():
    """验证 kwargs 可透传，且不同 kwargs 会被视为不同调用。"""
    warning_once = _get_warning_once()
    logger = _RecorderLogger()

    warning_once(logger, "kw-message", stacklevel=2)
    warning_once(logger, "kw-message", stacklevel=3)

    assert len(logger.calls) == 2
    assert logger.calls[0][0] == ("kw-message",)
    assert logger.calls[0][1] == {"stacklevel": 2}
    assert logger.calls[1][0] == ("kw-message",)
    assert logger.calls[1][1] == {"stacklevel": 3}


def test_warning_once_none_logger_raises_attribute_error():
    """验证 logger_obj 为 None 时会抛出属性异常。"""
    warning_once = _get_warning_once()

    with pytest.raises(AttributeError):
        warning_once(None, "invalid logger")


def test_warning_once_missing_message_raises_type_error():
    """验证缺少 message 参数时会抛出 TypeError。"""
    warning_once = _get_warning_once()
    logger = logging.Logger("warning-once-missing-message")

    with pytest.raises(TypeError):
        warning_once(logger)


def test_warning_once_unhashable_kwargs_raise_type_error():
    """验证传入不可哈希 kwargs 时，lru_cache 会抛出 TypeError。"""
    warning_once = _get_warning_once()
    logger = _RecorderLogger()

    with pytest.raises(TypeError):
        warning_once(logger, "invalid kwargs", extra={"tag": "python"})
