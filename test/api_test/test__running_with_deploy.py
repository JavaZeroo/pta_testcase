"""
测试目的：
1. 验证 torch._running_with_deploy 在 NPU 环境中可导入、可调用。
2. 覆盖无参调用、额外位置参数/关键字参数的异常场景，以及返回值类型与默认返回值。
3. 通过构造 NPU 张量，确保用例确实在 NPU 环境中执行测试。

API 名称：torch._running_with_deploy

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| callable | 已覆盖 | 验证 API 对象可调用 |
| 参数传/不传 | 已覆盖 | 覆盖无参调用、传入位置参数、传入关键字参数 |
| 参数类型 | 已覆盖 | 覆盖 None、0、True、字符串、object() 等代表性额外参数类型 |
| 返回类型 | 已覆盖 | 验证无参调用返回 bool |
| 默认返回值 | 已覆盖 | 标准环境下验证返回 False |
| 异常场景 | 已覆盖 | 额外参数触发 TypeError |
| NPU 运行环境 | 已覆盖 | 通过创建 NPU 张量确保测试在 NPU 环境中执行 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| torch::deploy 真正部署态运行链路 | 当前环境为常规测试环境，重点验证 Python 侧 API 行为，不构造 deploy 运行时 |
| 复杂参数组合（多个位置/关键字参数混合） | 该 API 仅支持无参调用，任何额外参数都应触发 TypeError，已用代表性样例覆盖 |
| None/非 None 作为合法输入的分支 | 该 API 无参数，不存在合法的 None/非 None 入参分支，仅作为非法额外参数样例覆盖 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 环境中执行 torch._running_with_deploy 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 环境中执行 torch._running_with_deploy 测试。")


def _require_api():
    _require_npu()
    if not hasattr(torch, "_running_with_deploy"):
        pytest.skip("当前环境不存在 torch._running_with_deploy，无法执行对应测试。")


@pytest.fixture()
def npu_sentinel():
    _require_npu()
    sentinel = torch.tensor([1], device=torch.device("npu:0"))
    assert sentinel.device.type == "npu"
    return sentinel


def test_running_with_deploy_callable(npu_sentinel):
    """验证 API 对象可调用，且测试在 NPU 环境中执行。"""
    _require_api()
    assert npu_sentinel.device.type == "npu"
    assert callable(torch._running_with_deploy)


def test_running_with_deploy_no_arg_returns_bool_and_false(npu_sentinel):
    """验证无参调用的返回类型为 bool，并在标准环境下返回 False。"""
    _require_api()
    assert npu_sentinel.device.type == "npu"

    result = torch._running_with_deploy()

    assert isinstance(result, bool)
    assert result is False


@pytest.mark.parametrize("bad_arg", [None, 0, True, "deploy", object()])
def test_running_with_deploy_with_argument_raises_type_error(npu_sentinel, bad_arg):
    """验证传入额外参数时抛出 TypeError。"""
    _require_api()
    assert npu_sentinel.device.type == "npu"

    with pytest.raises(TypeError):
        torch._running_with_deploy(bad_arg)


@pytest.mark.parametrize("bad_kwargs", [{"flag": None}, {"flag": 0}, {"flag": True}])
def test_running_with_deploy_with_keyword_argument_raises_type_error(npu_sentinel, bad_kwargs):
    """验证传入关键字参数时抛出 TypeError。"""
    _require_api()
    assert npu_sentinel.device.type == "npu"

    with pytest.raises(TypeError):
        torch._running_with_deploy(**bad_kwargs)
