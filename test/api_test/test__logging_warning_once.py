# 测试目的：验证 torch._logging.warning_once 在 NPU 环境中的功能行为
# API 名称：torch._logging.warning_once
#
# 覆盖的参数维度：
#
# | 覆盖维度           | 说明                                                     | 覆盖情况                                      |
# |--------------------|----------------------------------------------------------|-----------------------------------------------|
# | 空/非空（None 或其他值） | logger_obj 为真实 logger 对象（非 None）             | 覆盖非空 logger，不覆盖 None（实际无意义）     |
# | 枚举选项           | N/A（无枚举型入参）                                      | N/A                                           |
# | 参数类型           | *args 传入字符串/格式化串+参数；**kwargs 传入 exc_info等 | 覆盖纯字符串、格式化多参数、关键字参数路径     |
# | 传参与不传参       | kwargs 可选参数 exc_info、stacklevel 传入与不传入        | 已覆盖                                        |
# | 等价类/边界值      | 不同消息字符串（等价类）；相同消息重复调用（缓存边界）   | 已覆盖                                        |
# | 正常传参场景       | 合法 logger + 消息字符串，验证可调用、返回值为 None      | 已覆盖                                        |
# | 异常传参场景       | N/A（文档/参考测试中无稳定异常抛出证据）                 | 不覆盖                                        |
#
# 未覆盖项及原因：
# - logger_obj=None：源码直接调用 logger_obj.warning()，传入 None 会抛 AttributeError，
#   但文档未说明这是预期行为，且无参考测试，故不写异常用例。
# - 格式化字符串参数（%s 占位符路径）：属于 logging 模块标准行为，非该 API 特有，故省略。

import logging
import pytest

import torch
import torch_npu  # noqa: F401


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _make_logger(name: str) -> logging.Logger:
    """创建一个带 NullHandler 的测试用 Logger，避免日志输出干扰测试结果。"""
    logger = logging.getLogger(name)
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.WARNING)
    return logger


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_warning_once_cache():
    """每个测试前后清空 lru_cache，防止跨用例缓存污染。"""
    torch._logging.warning_once.cache_clear()
    yield
    torch._logging.warning_once.cache_clear()


# ---------------------------------------------------------------------------
# 存在性检查
# ---------------------------------------------------------------------------

def test_api_exists():
    """验证 torch._logging.warning_once 可通过属性访问获取，并且是可调用对象。"""
    assert hasattr(torch._logging, "warning_once"), (
        "torch._logging.warning_once not found in this torch version"
    )
    assert callable(torch._logging.warning_once)


# ---------------------------------------------------------------------------
# 正常调用路径
# ---------------------------------------------------------------------------

def test_return_value_is_none():
    """验证 warning_once 返回值为 None。"""
    logger = _make_logger("test_return_none")
    result = torch._logging.warning_once(logger, "unique message for return value test")
    assert result is None


def test_callable_with_message_string():
    """验证使用合法 logger 和字符串消息时 API 可正常调用。"""
    logger = _make_logger("test_callable_basic")
    # 不断言 warning 被调用次数，仅确认无异常
    torch._logging.warning_once(logger, "basic callable test message")


def test_warning_emitted_once_for_same_message(caplog):
    """验证对相同参数的重复调用只触发一次 warning（lru_cache 语义）。"""
    logger_name = "test_cache_same_msg"
    logger = _make_logger(logger_name)

    # caplog 需要 propagate=True 才能捕获
    logger.propagate = True

    with caplog.at_level(logging.WARNING, logger=logger_name):
        torch._logging.warning_once(logger, "cache_test: identical message XYZ")
        torch._logging.warning_once(logger, "cache_test: identical message XYZ")
        torch._logging.warning_once(logger, "cache_test: identical message XYZ")

    # 相同消息只应出现 1 次
    matching = [r for r in caplog.records if "identical message XYZ" in r.message]
    assert len(matching) == 1, (
        f"Expected 1 warning record, got {len(matching)}"
    )


def test_different_messages_each_emitted_once(caplog):
    """验证不同消息字符串各自独立触发一次 warning。"""
    logger_name = "test_diff_msgs"
    logger = _make_logger(logger_name)
    logger.propagate = True

    with caplog.at_level(logging.WARNING, logger=logger_name):
        torch._logging.warning_once(logger, "diff_msg_test: message A")
        torch._logging.warning_once(logger, "diff_msg_test: message B")
        torch._logging.warning_once(logger, "diff_msg_test: message A")  # 重复，不触发
        torch._logging.warning_once(logger, "diff_msg_test: message B")  # 重复，不触发

    records_a = [r for r in caplog.records if "message A" in r.message]
    records_b = [r for r in caplog.records if "message B" in r.message]

    assert len(records_a) == 1, f"message A: expected 1, got {len(records_a)}"
    assert len(records_b) == 1, f"message B: expected 1, got {len(records_b)}"


def test_callable_with_format_string_and_multiple_args(caplog):
    """验证使用格式化字符串 + 多个位置参数时 API 可正常调用（*args 透传给 logger.warning）。"""
    logger_name = "test_format_multi_args"
    logger = _make_logger(logger_name)
    logger.propagate = True

    with caplog.at_level(logging.WARNING, logger=logger_name):
        torch._logging.warning_once(
            logger, "value is %s and count is %d", "hello", 42
        )

    matching = [r for r in caplog.records if "value is hello" in r.message]
    assert len(matching) == 1


def test_kwargs_exc_info():
    """验证传入 exc_info 关键字参数时 API 可正常调用。"""
    logger = _make_logger("test_kwargs_exc_info")
    try:
        raise ValueError("test error for exc_info")
    except ValueError:
        # exc_info=True 会捕获当前异常信息
        result = torch._logging.warning_once(
            logger, "kwargs test: exc_info message", exc_info=True
        )
    assert result is None


def test_kwargs_stacklevel():
    """验证传入 stacklevel 关键字参数时 API 可正常调用。"""
    logger = _make_logger("test_kwargs_stacklevel")
    result = torch._logging.warning_once(
        logger, "kwargs test: stacklevel message", stacklevel=2
    )
    assert result is None


def test_kwargs_not_passed():
    """验证不传任何关键字参数时 API 可正常调用（使用全默认路径）。"""
    logger = _make_logger("test_no_kwargs")
    result = torch._logging.warning_once(logger, "no kwargs test message")
    assert result is None


def test_cache_info_increments():
    """验证 lru_cache 的 cache_info 在缓存命中时统计正确。"""
    logger = _make_logger("test_cache_info")

    # cache 已在 fixture 中清空
    torch._logging.warning_once(logger, "cache_info_test unique msg")
    info_after_first = torch._logging.warning_once.cache_info()
    assert info_after_first.currsize >= 1

    torch._logging.warning_once(logger, "cache_info_test unique msg")
    info_after_second = torch._logging.warning_once.cache_info()
    # 第二次命中缓存，hits 应 +1
    assert info_after_second.hits > info_after_first.hits


def test_cache_clear_resets_behavior(caplog):
    """验证 cache_clear() 后相同消息可再次触发 warning。"""
    logger_name = "test_cache_clear"
    logger = _make_logger(logger_name)
    logger.propagate = True

    with caplog.at_level(logging.WARNING, logger=logger_name):
        torch._logging.warning_once(logger, "cache_clear_test: reset message")

    count_before_clear = len(
        [r for r in caplog.records if "reset message" in r.message]
    )
    assert count_before_clear == 1

    # 清空缓存后再次调用，应该再次触发
    torch._logging.warning_once.cache_clear()
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger=logger_name):
        torch._logging.warning_once(logger, "cache_clear_test: reset message")

    count_after_clear = len(
        [r for r in caplog.records if "reset message" in r.message]
    )
    assert count_after_clear == 1
