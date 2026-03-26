# 测试目的：验证 torch.__future__.get_swap_module_params_on_conversion 在 NPU 环境下可正常调用，
#           返回类型为 bool，并与 set_swap_module_params_on_conversion 联动行为正确。
#
# API 名称：torch.__future__.get_swap_module_params_on_conversion
#
# 覆盖参数维度：
#
# | 覆盖维度         | 说明                                           | 覆盖情况                        |
# |------------------|------------------------------------------------|---------------------------------|
# | 空/非空           | 该 API 无参数，N/A                             | N/A                             |
# | 枚举选项          | 该 API 无参数，N/A                             | N/A                             |
# | 参数类型          | 该 API 无参数，N/A                             | N/A                             |
# | 传参与不传参      | 该 API 无参数，N/A                             | N/A                             |
# | 等价类/边界值     | 返回值只有 True/False 两种，全部覆盖           | 已覆盖                          |
# | 正常传参场景      | 默认调用、与 setter 联动后调用                 | 已覆盖                          |
# | 异常传参场景      | 无参数，API 不会抛出任何异常，N/A              | N/A                             |
#
# 未覆盖项：
# - 无。该 API 源码为单行 getter，无任何分支，所有可测试路径均已覆盖。

import pytest
import torch
import torch_npu  # noqa: F401


# ---------------------------------------------------------------------------
# 环境前置检查（模块级，不在单个测试中重复）
# ---------------------------------------------------------------------------
if not hasattr(torch, "__future__"):
    pytest.skip(
        "torch.__future__ 不存在，当前 PyTorch 版本不支持此 API",
        allow_module_level=True,
    )

if not hasattr(torch.__future__, "get_swap_module_params_on_conversion"):
    pytest.skip(
        "torch.__future__.get_swap_module_params_on_conversion 不存在，"
        "当前 PyTorch 版本未暴露该 API",
        allow_module_level=True,
    )

if not torch.npu.is_available():
    pytest.skip("NPU 设备不可用，跳过全部测试", allow_module_level=True)


# ---------------------------------------------------------------------------
# 辅助 fixture：每个测试结束后将全局开关恢复为 False，避免测试间相互污染
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def restore_default():
    """在每个测试结束后将 swap_module_params_on_conversion 重置为默认值 False。"""
    yield
    torch.__future__.set_swap_module_params_on_conversion(False)


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestGetSwapModuleParamsOnConversionDefault:
    """测试默认返回值行为。"""

    def test_returns_bool(self):
        """API 调用后返回值类型必须是 bool。"""
        result = torch.__future__.get_swap_module_params_on_conversion()
        assert isinstance(result, bool)

    def test_default_value_is_false(self):
        """未调用 setter 时，默认返回值应为 False。"""
        result = torch.__future__.get_swap_module_params_on_conversion()
        assert result is False

    def test_callable_on_npu_environment(self):
        """在 NPU 环境中 API 可正常调用，无需 NPU tensor，但需 NPU 可用。"""
        # 确认 NPU 可用后调用，验证 NPU 环境不影响此 API 的可调用性
        assert torch.npu.is_available()
        result = torch.__future__.get_swap_module_params_on_conversion()
        assert isinstance(result, bool)


class TestGetSwapModuleParamsOnConversionWithSetter:
    """测试与 set_swap_module_params_on_conversion 联动的行为。"""

    def test_get_returns_true_after_set_true(self):
        """调用 set_swap_module_params_on_conversion(True) 后，get 应返回 True。"""
        torch.__future__.set_swap_module_params_on_conversion(True)
        result = torch.__future__.get_swap_module_params_on_conversion()
        assert result is True

    def test_get_returns_false_after_set_false(self):
        """调用 set_swap_module_params_on_conversion(False) 后，get 应返回 False。"""
        # 先设为 True，再设回 False，确保 setter 真正生效
        torch.__future__.set_swap_module_params_on_conversion(True)
        torch.__future__.set_swap_module_params_on_conversion(False)
        result = torch.__future__.get_swap_module_params_on_conversion()
        assert result is False

    def test_toggle_true_false_returns_correct_values(self):
        """多次切换 setter，getter 每次都应反映最新设置的值。"""
        torch.__future__.set_swap_module_params_on_conversion(True)
        assert torch.__future__.get_swap_module_params_on_conversion() is True

        torch.__future__.set_swap_module_params_on_conversion(False)
        assert torch.__future__.get_swap_module_params_on_conversion() is False

        torch.__future__.set_swap_module_params_on_conversion(True)
        assert torch.__future__.get_swap_module_params_on_conversion() is True

    def test_return_type_is_bool_after_set_true(self):
        """set 为 True 后，get 返回值仍应是 bool 类型。"""
        torch.__future__.set_swap_module_params_on_conversion(True)
        result = torch.__future__.get_swap_module_params_on_conversion()
        assert isinstance(result, bool)


class TestGetSwapModuleParamsOnConversionWithNNModule:
    """测试在实际使用 nn.Module 的 NPU 场景中，get 的语义是否正确反映。"""

    def test_module_conversion_with_swap_false(self):
        """swap 为 False 时，nn.Module.to(npu) 可正常执行，get 返回 False。"""
        torch.__future__.set_swap_module_params_on_conversion(False)
        assert torch.__future__.get_swap_module_params_on_conversion() is False

        import torch.nn as nn
        model = nn.Linear(4, 4)
        # .to(npu) 触发参数转换，验证此时 get 仍正确反映全局状态
        model = model.to("npu")
        assert torch.__future__.get_swap_module_params_on_conversion() is False

    def test_module_conversion_with_swap_true(self):
        """swap 为 True 时，nn.Module.to(npu) 可正常执行，get 返回 True。"""
        torch.__future__.set_swap_module_params_on_conversion(True)
        assert torch.__future__.get_swap_module_params_on_conversion() is True

        import torch.nn as nn
        model = nn.Linear(4, 4)
        model = model.to("npu")
        assert torch.__future__.get_swap_module_params_on_conversion() is True
