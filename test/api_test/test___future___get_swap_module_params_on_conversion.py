"""
测试目的：
1. 验证 torch.__future__.get_swap_module_params_on_conversion 在 NPU 测试环境中可正常调用，且返回值类型为 bool。
2. 验证该 API 文档声明的默认值为 False，并在全新 Python 进程中进行校验，避免受进程内全局状态污染。
3. 验证该 getter 与 torch.__future__.set_swap_module_params_on_conversion 配对使用时，True/False 两个主要枚举值可被正确读取。
4. 验证无参正常调用、错误传参异常、全局状态恢复等基础功能场景。

API 名称：torch.__future__.get_swap_module_params_on_conversion

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 无参调用 | 已覆盖 | 直接调用 get_swap_module_params_on_conversion() |
| 默认值 | 已覆盖 | 在全新 Python 进程中验证默认返回 False |
| 返回类型 | 已覆盖 | 断言返回值为 bool |
| 主要枚举值 | 已覆盖 | 通过 set_swap_module_params_on_conversion(True/False) 触发两种状态 |
| None / 非None | 已覆盖 | 错误传参分别使用 None 和非 None 值，均验证抛出 TypeError |
| 主要类型 | 已覆盖 | 错误传参与 bool / int / 关键字参数等类型组合 |
| 正常场景 | 已覆盖 | 默认值读取、无参调用与状态切换后读取 |
| 异常场景 | 已覆盖 | 使用 pytest.raises 验证 TypeError |
| 边界值 | 已覆盖 | True / False 作为全局开关的边界状态 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 多线程并发读写 | 该 API 为全局开关，当前用例聚焦单线程功能与状态恢复 |
| 与 nn.Module.to / load_state_dict 等实际转换行为的联动效果 | 当前仅验证 getter/setter 的接口级行为，不扩展到更大规模集成路径 |
| 多卡 NPU 场景 | 当前用例只需验证单卡 NPU 上的基础行为即可满足覆盖目标 |
"""

import subprocess
import sys

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu；本用例仅在 NPU 测试环境下校验 torch.__future__ 状态查询接口。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用；本用例仅在 NPU 测试环境下校验 torch.__future__ 状态查询接口。")


@pytest.fixture()
def npu_future_flag_restore():
    _require_npu()
    probe = torch.tensor([1], device=torch.device("npu:0"))
    assert probe.device.type == "npu"

    original = torch.__future__.get_swap_module_params_on_conversion()
    yield original
    torch.__future__.set_swap_module_params_on_conversion(original)


def test_get_swap_module_params_on_conversion_default_returns_false_in_fresh_process():
    """验证文档声明的默认值为 False，且结果不受当前测试进程全局状态影响。"""
    _require_npu()
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import torch; "
                "import torch_npu; "
                "print(torch.__future__.get_swap_module_params_on_conversion())"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "False"


def test_get_swap_module_params_on_conversion_returns_current_bool(npu_future_flag_restore):
    """验证当前状态下无参调用返回 bool，并与进程内当前值一致。"""
    original = npu_future_flag_restore
    result = torch.__future__.get_swap_module_params_on_conversion()

    assert isinstance(result, bool)
    assert result == original


@pytest.mark.parametrize("set_value", [True, False])
def test_get_swap_module_params_on_conversion_round_trip(npu_future_flag_restore, set_value):
    """验证 set/get 往返读取：设置 True/False 后能够读回对应布尔值。"""
    torch.__future__.set_swap_module_params_on_conversion(set_value)
    result = torch.__future__.get_swap_module_params_on_conversion()

    assert isinstance(result, bool)
    assert result is set_value


@pytest.mark.parametrize(
    "call_args, call_kwargs",
    [
        ((None,), {}),
        ((1,), {}),
        ((), {"value": True}),
        ((), {"value": None}),
    ],
)
def test_get_swap_module_params_on_conversion_wrong_args_raises(
    npu_future_flag_restore, call_args, call_kwargs
):
    """验证错误传参时抛出 TypeError。"""
    with pytest.raises(TypeError):
        torch.__future__.get_swap_module_params_on_conversion(*call_args, **call_kwargs)
