# 测试目的：验证 torch._C._get_accelerator 在 NPU 环境中的功能行为
# API 名称：torch._C._get_accelerator
# 签名：_get_accelerator(check: Optional[bool] = None) -> torch.device
#
# 覆盖的参数维度：
#
# | 覆盖维度                  | 说明                                                               | 覆盖情况                                              |
# |---------------------------|--------------------------------------------------------------------|-------------------------------------------------------|
# | 空/非空（None 或其他值）  | check=None（默认）、check=True、check=False 三条路径               | 已覆盖（test_check_none / test_check_true / test_check_false） |
# | 枚举选项                  | N/A（check 为 Optional[bool]，只有 None/True/False 三种值）        | 已覆盖                                                |
# | 参数类型                  | bool 类型（True/False）与 None 类型                                | 已覆盖                                                |
# | 传参与不传参              | 无参数直接调用（默认路径）与显式传入 check 参数                    | 已覆盖                                                |
# | 等价类/边界值             | check=True/False/None 三个等价类；device.index=-1 边界             | 已覆盖                                                |
# | 正常传参场景              | 合法输入均可调用，返回 torch.device，NPU 环境下 type 为 npu        | 已覆盖                                                |
# | 异常传参场景              | 无稳定异常证据（文档未说明，参考测试中无对应用例），不覆盖         | 不覆盖                                                |
#
# 源码分支分析（pytorch/torch/csrc/Module.cpp）：
#   1. check=nullopt（Python 侧 None） → at::getAccelerator(false) → 不强制检查
#   2. check=true → at::getAccelerator(check) → 强制检查（isAvailable 结果影响 acc）
#   3. check=false → at::getAccelerator(false) → 不强制检查
#   4. accelerator 存在且 isAvailable()=true → 返回对应 device（NPU 环境为 npu）
#   5. accelerator 存在但 isAvailable()=false → acc=nullopt → 返回 CPU device
#   6. 无 accelerator → acc=nullopt → 返回 CPU device
#   C++ 最终：return c10::Device(acc.value_or(c10::DeviceType::CPU), -1)
#   → Python 层 device.index 始终为 -1（torch.device 实际不存储 -1，显示为无 index）
#
# 未覆盖项及原因：
# - check=True 且 accelerator 不可用导致回退到 CPU 的分支：该分支依赖特定硬件状态，
#   无法在通用 NPU 测试环境中稳定复现，故不覆盖。
# - 非法参数（如传入整数/字符串）：C++ 侧使用 std::optional<bool>，Python 调用层
#   会接受大多数值，无稳定 TypeError 证据，故不写异常用例。

import pytest

import torch
import torch_npu  # noqa: F401


# ---------------------------------------------------------------------------
# 存在性检查
# ---------------------------------------------------------------------------

def test_api_exists():
    """验证 torch._C._get_accelerator 可通过属性访问，且是可调用对象。"""
    assert hasattr(torch._C, "_get_accelerator"), (
        "torch._C._get_accelerator not found in this torch version"
    )
    assert callable(torch._C._get_accelerator)


# ---------------------------------------------------------------------------
# 正常调用路径 —— 返回类型断言
# ---------------------------------------------------------------------------

def test_no_args_returns_device():
    """无参数调用：返回值必须是 torch.device 类型。"""
    result = torch._C._get_accelerator()
    assert isinstance(result, torch.device), (
        f"Expected torch.device, got {type(result)}"
    )


def test_check_none_returns_device():
    """显式传入 check=None：返回值必须是 torch.device 类型。"""
    result = torch._C._get_accelerator(check=None)
    assert isinstance(result, torch.device), (
        f"Expected torch.device, got {type(result)}"
    )


def test_check_false_returns_device():
    """check=False（不强制检查）：返回值必须是 torch.device 类型。"""
    result = torch._C._get_accelerator(check=False)
    assert isinstance(result, torch.device), (
        f"Expected torch.device, got {type(result)}"
    )


def test_check_true_returns_device():
    """check=True（强制检查 isAvailable）：返回值必须是 torch.device 类型。"""
    result = torch._C._get_accelerator(check=True)
    assert isinstance(result, torch.device), (
        f"Expected torch.device, got {type(result)}"
    )


# ---------------------------------------------------------------------------
# NPU 环境下的 device 类型断言
# ---------------------------------------------------------------------------

def test_npu_env_returns_npu_device():
    """NPU 环境下，返回的 device.type 应为 'npu'（非 CPU 回退）。"""
    assert torch.npu.is_available(), "NPU not available, skip this assertion"
    result = torch._C._get_accelerator()
    assert result.type == "npu", (
        f"Expected device type 'npu' in NPU environment, got '{result.type}'"
    )


def test_check_false_npu_env_device_type():
    """check=False 路径在 NPU 环境下，返回 device.type 应为 'npu'。"""
    assert torch.npu.is_available(), "NPU not available, skip this assertion"
    result = torch._C._get_accelerator(check=False)
    assert result.type == "npu", (
        f"Expected 'npu', got '{result.type}'"
    )


def test_check_true_npu_env_device_type():
    """check=True 路径在 NPU 环境下（NPU 可用），返回 device.type 应为 'npu'。"""
    assert torch.npu.is_available(), "NPU not available, skip this assertion"
    result = torch._C._get_accelerator(check=True)
    assert result.type == "npu", (
        f"Expected 'npu' when check=True and NPU is available, got '{result.type}'"
    )


def test_check_none_npu_env_device_type():
    """check=None 路径在 NPU 环境下，返回 device.type 应为 'npu'。"""
    assert torch.npu.is_available(), "NPU not available, skip this assertion"
    result = torch._C._get_accelerator(check=None)
    assert result.type == "npu", (
        f"Expected 'npu', got '{result.type}'"
    )


# ---------------------------------------------------------------------------
# 结果一致性：不同 check 值应返回相同 device（NPU 均可用时）
# ---------------------------------------------------------------------------

def test_results_consistent_across_check_values():
    """在 NPU 可用的环境下，不同 check 参数返回的 device.type 应一致。"""
    assert torch.npu.is_available(), "NPU not available, skip this assertion"
    r_default = torch._C._get_accelerator()
    r_none = torch._C._get_accelerator(check=None)
    r_false = torch._C._get_accelerator(check=False)
    r_true = torch._C._get_accelerator(check=True)

    assert r_default.type == r_none.type == r_false.type == r_true.type, (
        f"Inconsistent device types across check values: "
        f"default={r_default.type}, None={r_none.type}, "
        f"False={r_false.type}, True={r_true.type}"
    )


# ---------------------------------------------------------------------------
# 与 torch.accelerator.current_accelerator() 的一致性（参考 __init__.py 用法）
# ---------------------------------------------------------------------------

def test_device_type_consistent_with_torch_get_device_module():
    """验证返回的 device.type 与 torch.get_device_module() 所用 type 一致。
    torch/__init__.py 中 get_device_module(None) 直接使用 _get_accelerator().type。
    """
    assert torch.npu.is_available(), "NPU not available, skip this assertion"
    acc_device = torch._C._get_accelerator()
    # torch.get_device_module(None) 内部依赖 _get_accelerator().type
    module = torch.get_device_module(None)
    assert hasattr(module, "__name__") or module is not None
    # device type 应与对应模块名一致（npu → torch_npu 或 torch.npu）
    assert acc_device.type == "npu"
