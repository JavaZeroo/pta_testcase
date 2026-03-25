"""
测试目的：
1. 验证 torch._dynamo.compiled_autograd.compiled_autograd_enabled_force_eager 可导入、可读取，且默认类型和值符合预期。
2. 验证在 torch.compiler.set_stance("force_eager") 作用域内，该标志会被正确置位，并在退出后恢复。
3. 验证在 NPU Tensor 的 backward 场景下，force_eager 标志切换不影响正常反向传播。

API 名称：torch._dynamo.compiled_autograd.compiled_autograd_enabled_force_eager

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 参数个数 | 已覆盖 | 该 API 本身为无参数 bool 常量，直接读取即可 |
| 传参/不传 | 不适用 | 目标 API 不接受参数 |
| 主要类型 | 已覆盖 | 验证目标值为 bool |
| 主要枚举值 | 已覆盖 | 通过 torch.compiler.set_stance("force_eager") 覆盖主要 stance 分支 |
| 正常场景 | 已覆盖 | 在 force_eager 上下文内读取标志、执行 NPU backward、退出后恢复 |
| 异常场景 | 不适用 | 目标 API 为 bool 常量，不存在独立参数校验或可调用异常场景 |
| NPU 设备 | 已覆盖 | 使用 npu:0 张量执行 backward 验证 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| compiled_autograd 的非 force_eager 编译链路细节 | 本用例聚焦 force_eager 标志语义与基础上下文行为，不展开更复杂的编译产物校验 |
| 多卡 / 分布式 NPU 场景 | 当前仅验证单卡 NPU 基础功能，避免引入额外硬件与通信依赖 |
| 数值正确性校验 | 该 API 关注状态标志切换，不做梯度数值精确比对 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu_and_api():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上测试 compiled_autograd_enabled_force_eager。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上测试 compiled_autograd_enabled_force_eager。")
    if not hasattr(torch, "_dynamo") or not hasattr(torch._dynamo, "compiled_autograd"):
        pytest.skip("当前环境缺少 torch._dynamo.compiled_autograd，无法测试 compiled_autograd_enabled_force_eager。")
    if not hasattr(torch._dynamo.compiled_autograd, "compiled_autograd_enabled_force_eager"):
        pytest.skip("当前环境缺少 compiled_autograd_enabled_force_eager API，无法继续测试。")


def _dummy_compiler_fn(*args, **kwargs):
    return None


def test_compiled_autograd_force_eager_default_bool_and_type():
    _require_npu_and_api()
    compiled_autograd = torch._dynamo.compiled_autograd

    assert hasattr(compiled_autograd, "compiled_autograd_enabled_force_eager")
    assert type(compiled_autograd.compiled_autograd_enabled_force_eager) is bool
    assert compiled_autograd.compiled_autograd_enabled_force_eager is False


def test_compiled_autograd_force_eager_enter_exit_and_npu_backward():
    _require_npu_and_api()
    compiled_autograd = torch._dynamo.compiled_autograd

    x = torch.randn(4, device=torch.device("npu:0"), requires_grad=True)
    assert x.device.type == "npu"
    assert compiled_autograd.compiled_autograd_enabled_force_eager is False

    with torch.compiler.set_stance("force_eager"):
        with compiled_autograd._enable(_dummy_compiler_fn):
            assert compiled_autograd.compiled_autograd_enabled_force_eager is True
            y = (x * 2).sum()
            y.backward()
            assert x.grad is not None
            assert isinstance(x.grad, torch.Tensor)
            assert x.grad.device.type == "npu"
            assert x.grad.device.index == 0

        assert compiled_autograd.compiled_autograd_enabled_force_eager is False

    assert compiled_autograd.compiled_autograd_enabled_force_eager is False
