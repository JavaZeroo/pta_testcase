"""
测试目的：
1. 验证 torch._dynamo.compiled_autograd.in_compiled_autograd_region 可正常导入并可直接读取。
2. 验证该 API 作为无参数布尔常量，在编译式自动求导区域外默认返回 False，且类型为 bool。
3. 验证在 compiled_autograd._enable 上下文中执行 NPU backward 时，可观测到区域标志为 True，并在退出后恢复为 False。

API 名称：torch._dynamo.compiled_autograd.in_compiled_autograd_region

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 参数个数 | 已覆盖 | 该 API 为无参数布尔常量，直接读取即可 |
| 传参/不传 | 不适用 | 该 API 不接受参数 |
| None/非None | 不适用 | 该 API 不接受参数，无法构造该维度 |
| 主要枚举值 | 不适用 | 该 API 不接受枚举参数 |
| 主要类型 | 已覆盖 | 返回值类型为 bool |
| 正常场景 | 已覆盖 | 区域外为 False，区域内可观测到 True |
| 异常场景 | 不适用 | 该 API 为 bool 常量，无参数且无合法调用形式 |
| NPU 设备 | 已覆盖 | 使用 npu:0 张量执行验证 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值正确性 | 该 API 仅表示区域状态，不涉及数值结果校验 |
| 多 NPU 卡/分布式场景 | 当前用例聚焦单卡 NPU 的接口行为，未依赖多卡环境 |
| 更复杂的嵌套编译链路 | 该 API 的核心关注点是区域状态，本文件避免引入过多编译链路依赖以保持稳定 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu_and_compiled_autograd():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行测试。")

    try:
        from torch._dynamo import compiled_autograd
    except (ImportError, ModuleNotFoundError, AttributeError) as exc:  # pragma: no cover - 仅用于环境缺失时跳过
        pytest.skip(f"当前环境无法导入 torch._dynamo.compiled_autograd，原因：{exc}")

    if not hasattr(compiled_autograd, "in_compiled_autograd_region"):
        pytest.skip("当前环境缺少 torch._dynamo.compiled_autograd.in_compiled_autograd_region。")
    return compiled_autograd


def _make_npu_leaf_tensor():
    return torch.tensor([1.0, 2.0, 3.0], device=torch.device("npu:0"), requires_grad=True)


def test_in_compiled_autograd_region_default_false_and_type_bool():
    compiled_autograd = _require_npu_and_compiled_autograd()

    probe = torch.ones(1, device=torch.device("npu:0"))
    assert probe.device.type == "npu"

    assert hasattr(compiled_autograd, "in_compiled_autograd_region")
    assert type(compiled_autograd.in_compiled_autograd_region) is bool
    assert compiled_autograd.in_compiled_autograd_region is False


def test_in_compiled_autograd_region_inside_enable_context_observed_true():
    compiled_autograd = _require_npu_and_compiled_autograd()
    if not hasattr(compiled_autograd, "_enable"):
        pytest.skip("当前环境缺少 compiled_autograd._enable，无法验证上下文内区域状态。")

    x = _make_npu_leaf_tensor()
    seen_flags = []

    def record_region_flag(grad):
        seen_flags.append(compiled_autograd.in_compiled_autograd_region)
        return grad

    x.register_hook(record_region_flag)
    loss = (x * 2).sum()

    with torch.autograd.set_multithreading_enabled(False):
        with compiled_autograd._enable(lambda gm: gm):
            loss.backward()

    assert seen_flags, "应当在 backward hook 中观测到至少一次区域状态读取。"
    assert all(type(flag) is bool for flag in seen_flags)
    assert any(seen_flags)
    assert compiled_autograd.in_compiled_autograd_region is False
