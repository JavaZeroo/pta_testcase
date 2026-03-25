"""
测试目的：
1. 验证 torch._dynamo.config 模块可导入、可访问；当前用例额外确认测试运行环境可使用 NPU，但 API 行为本身不依赖 NPU。
2. 验证该配置模块中稳定公共配置项在当前版本下的代表性类型与 None/非 None 场景。
3. 验证 torch._dynamo.config.patch 的“传参/不传参”用法、正常回环与异常场景。
4. 验证 get_hash 对“编译忽略项/非忽略项”的差异表现。

API 名称：torch._dynamo.config

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 模块导入 | 已覆盖 | 使用 importlib 导入 torch._dynamo.config |
| NPU 环境确认 | 已覆盖 | 创建 NPU Tensor 仅用于确认当前测试环境可用 NPU，不将其视为 API 的 NPU 专属行为 |
| 公共配置项存在性 | 已覆盖 | 直接断言 verbose、suppress_errors、recompile_limit 等稳定代表性配置项存在 |
| 代表性类型样本 | 已覆盖 | 仅覆盖当前文件中选取的稳定属性上的 bool / int / float / str / list / set / dict / NoneType 样本 |
| None / 非 None | 已覆盖 | 以 repro_after 为代表完成 None -> 非 None -> None 回环 |
| 参数传 / 不传 | 已覆盖 | 覆盖 patch()、patch(dict) / patch(kwargs) / patch("name", value) |
| 正常场景 | 已覆盖 | 属性读写、恢复、hash 对比 |
| 异常场景 | 已覆盖 | 缺失配置项访问与非法 patch 键均使用 pytest.raises |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 全部私有/实验性配置项 | torch._dynamo.config 的内部项和版本差异较大，优先覆盖稳定的代表性公共项 |
| 配置值的具体数值语义 | 本测试聚焦 API 行为与可用性，不做具体数值正确性校验 |
| 与 torch.compile 的完整联动效果 | 避免引入编译图行为差异导致测试脆弱，当前仅验证配置模块自身行为 |
"""

from __future__ import annotations

import importlib

import pytest

import torch
import torch_npu  # noqa: F401

import torch._dynamo.config as cfg


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法执行本文件中的 NPU 环境确认步骤。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法执行本文件中的 NPU 环境确认步骤。")


@pytest.fixture(scope="module")
def npu_tensor():
    _require_npu()
    tensor = torch.tensor([1.0], device=torch.device("npu:0"))
    assert tensor.device.type == "npu"
    return tensor


def test_dynamo_config_module_importable_on_npu(npu_tensor):
    """验证模块可导入，并确认当前测试运行环境可使用 NPU。"""
    imported = importlib.import_module("torch._dynamo.config")

    assert imported is cfg
    assert npu_tensor.device.type == "npu"


def test_dynamo_config_public_attributes_have_major_types(npu_tensor):
    """验证稳定代表性配置项存在且类型符合当前文件声明的样本覆盖。"""
    assert npu_tensor.device.type == "npu"

    type_groups = [
        (["verbose", "suppress_errors", "dynamic_shapes", "assume_static_by_default", "guard_nn_modules"], bool),
        (["recompile_limit", "cache_size_limit", "minimum_call_count"], int),
        (["repro_tolerance"], float),
        (["automatic_dynamic_shapes_mark_as", "base_dir", "numpy_default_float"], str),
        (["repro_after", "log_file_name", "automatic_dynamic_remote_pgo", "_custom_ops_profile"], type(None)),
        (["_autograd_backward_strict_mode_banned_ops", "_autograd_backward_strict_mode_conditional_banned_ops"], list),
        (["allowed_functions_module_string_ignorelist", "_save_config_ignore"], set),
        (["skipfiles_inline_module_allowlist", "compiled_autograd_kwargs_override"], dict),
    ]

    for names, expected_type in type_groups:
        for name in names:
            assert hasattr(cfg, name), f"torch._dynamo.config 应存在稳定配置项: {name}"
            value = getattr(cfg, name)
            if expected_type is int:
                assert isinstance(value, int) and not isinstance(value, bool)
            else:
                assert isinstance(value, expected_type)


def test_dynamo_config_patch_argument_forms_and_round_trip(npu_tensor):
    """验证 patch 的不传参、mapping 形式、kwargs 形式和字符串形式。"""
    assert npu_tensor.device.type == "npu"

    baseline_hash = cfg.get_hash()

    # 不传参：应保持不变
    with cfg.patch():
        assert cfg.get_hash() == baseline_hash

    # mapping 形式：优先验证 compile-ignored 配置项，hash 不应变化
    assert hasattr(cfg, "verbose"), "torch._dynamo.config 应存在稳定配置项: verbose"
    original_verbose = cfg.verbose
    with cfg.patch({"verbose": not original_verbose}):
        assert cfg.verbose is (not original_verbose)
        assert cfg.get_hash() == baseline_hash
    assert cfg.verbose == original_verbose

    # kwargs 形式：优先验证非忽略项，hash 应变化
    assert hasattr(cfg, "suppress_errors"), "torch._dynamo.config 应存在稳定配置项: suppress_errors"
    original_suppress_errors = cfg.suppress_errors
    with cfg.patch(suppress_errors=not original_suppress_errors):
        assert cfg.suppress_errors is (not original_suppress_errors)
        assert cfg.get_hash() != baseline_hash
    assert cfg.suppress_errors == original_suppress_errors

    # 字符串 + 值 形式：验证 None -> 非 None 回环
    assert hasattr(cfg, "repro_after"), "torch._dynamo.config 应存在稳定配置项: repro_after"
    original_repro_after = cfg.repro_after
    with cfg.patch("repro_after", "pytest_npu_marker"):
        assert cfg.repro_after == "pytest_npu_marker"
    assert cfg.repro_after == original_repro_after


def test_dynamo_config_invalid_patch_key_raises_attribute_error(npu_tensor):
    """验证非法 patch 键会抛出 AttributeError。"""
    assert npu_tensor.device.type == "npu"

    with pytest.raises(AttributeError):
        with cfg.patch("definitely_not_exist_for_test", True):
            pass


def test_dynamo_config_missing_attribute_raises_attribute_error(npu_tensor):
    """验证访问缺失配置项时抛出 AttributeError。"""
    assert npu_tensor.device.type == "npu"

    with pytest.raises(AttributeError):
        _ = cfg.__definitely_not_exist_for_test__
