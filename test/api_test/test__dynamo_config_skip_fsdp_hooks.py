"""
测试目的：
1. 验证 torch._dynamo.config.skip_fsdp_hooks 在 NPU 环境下可导入、可访问、可读写。
2. 验证该配置项的默认值类型为 bool。
3. 验证该配置项支持 bool 契约内的 True/False 写入并可恢复原值。
4. 所有测试先创建 NPU Tensor，确保测试实际在 NPU 后端运行。

API 名称：torch._dynamo.config.skip_fsdp_hooks

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| NPU 环境 | 已覆盖 | 创建 npu Tensor 并断言 device.type == "npu" |
| 属性存在性 | 已覆盖 | 直接读取 cfg.skip_fsdp_hooks |
| 默认值类型 | 已覆盖 | 断言默认值为 bool |
| 赋值场景 | 已覆盖 | 写入 True/False 后读回 |
| 类型覆盖 | 已覆盖 | 覆盖 bool |
| 参数传 / 不传 | 不适用 | 该 API 为配置常量，无函数参数 |
| 主要枚举 | 不适用 | 该 API 不是枚举类或枚举参数 |
| 语义正确性 | 未覆盖 | 仅验证配置项读写与类型行为，不校验 FSDP hooks 的实际语义效果 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| skip_fsdp_hooks 对 FSDP 编译/trace 行为的实际影响 | 需要完整分布式 FSDP 场景，当前用例聚焦配置项接口 |
| 多卡/多进程分布式效果 | 当前测试在单进程 NPU 环境下执行 |
| 非 bool 非法赋值的约束行为 | 当前最小修复仅保留与 bool 契约一致的读写场景 |
| 具体默认值是否始终固定 | 默认值可能随版本变化，测试仅校验其可读和类型 |
"""

import pytest

import torch
import torch_npu  # noqa: F401

import torch._dynamo.config as cfg


def _require_npu_tensor():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch._dynamo.config.skip_fsdp_hooks 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch._dynamo.config.skip_fsdp_hooks 测试。")

    npu_tensor = torch.ones(1, device=torch.device("npu:0"))
    assert npu_tensor.device.type == "npu"
    return npu_tensor


def _require_skip_fsdp_hooks():
    if not hasattr(cfg, "skip_fsdp_hooks"):
        pytest.fail("torch._dynamo.config.skip_fsdp_hooks not found")


def test_skip_fsdp_hooks_default_access_and_type_on_npu():
    """验证默认值可访问且类型为 bool。"""
    npu_tensor = _require_npu_tensor()
    assert npu_tensor.device.type == "npu"
    _require_skip_fsdp_hooks()

    value = getattr(cfg, "skip_fsdp_hooks")
    assert isinstance(value, bool)
    assert type(value) is bool


@pytest.mark.parametrize(
    "new_value, expected_type",
    [
        (True, bool),
        (False, bool),
    ],
)
def test_skip_fsdp_hooks_assignment_roundtrip_and_restore(new_value, expected_type):
    """验证写入典型类型后可读回，并在测试后恢复原值。"""
    npu_tensor = _require_npu_tensor()
    assert npu_tensor.device.type == "npu"
    _require_skip_fsdp_hooks()

    original_value = getattr(cfg, "skip_fsdp_hooks")
    try:
        setattr(cfg, "skip_fsdp_hooks", new_value)
        current_value = getattr(cfg, "skip_fsdp_hooks")
        assert current_value == new_value
        assert type(current_value) is expected_type
    finally:
        setattr(cfg, "skip_fsdp_hooks", original_value)
        assert getattr(cfg, "skip_fsdp_hooks") is original_value
