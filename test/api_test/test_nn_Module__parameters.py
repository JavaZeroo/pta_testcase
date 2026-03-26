# 测试目的：验证 torch.nn.Module._parameters 属性在 NPU 上的基本行为
# API 名称：torch.nn.Module._parameters
#
# 说明：_parameters 是 nn.Module 的内部属性，为 OrderedDict 类型，
# 存储模块的参数（nn.Parameter 实例）。由 __init__ 初始化，
# 通过 register_parameter() 或直接赋值 nn.Parameter 属性来填充。
# 该 API 无公开文档（source="not_found"），测试基于源码行为推断。
#
# 覆盖维度：
#
# | 覆盖维度           | 说明                                           | 覆盖情况                                          |
# |--------------------|------------------------------------------------|---------------------------------------------------|
# | 空/非空（None 或其他值）| None 参数与非 None 参数的注册路径              | 已覆盖：register_parameter(name, None) 与非 None  |
# | 枚举选项           | N/A（无枚举型入参）                             | N/A                                               |
# | 参数类型           | nn.Parameter（float）、None                    | 已覆盖                                            |
# | 传参与不传参       | N/A（_parameters 为属性，非调用接口）           | N/A                                               |
# | 等价类/边界值      | 空模块、单参数、多参数、参数覆盖写              | 已覆盖                                            |
# | 正常传参场景       | 初始化/注册/赋值/NPU 设备/覆盖写               | 已覆盖                                            |
# | 异常传参场景       | 无——内部属性访问无稳定异常路径                  | 未覆盖（无明确证据）                              |
#
# 未覆盖项及原因：
# - 异常场景（如 register_parameter 传非法名称）：PyTorch 对部分非法名称会抛 KeyError/ValueError，
#   但行为依赖 PyTorch 版本，且非 _parameters 属性本身的行为，故不覆盖。
# - 复数/半精度类型：属性行为与 float32 一致，无需单独验证。

import pytest
import torch
import torch.nn as nn
import torch_npu  # noqa: F401


# ---------------------------------------------------------------------------
# 辅助：检查 NPU 是否可用
# ---------------------------------------------------------------------------

def _npu_device():
    """返回 NPU device 对象，若不可用则 skip。"""
    if not torch.npu.is_available():
        pytest.skip("NPU device is not available")
    return torch.device("npu", 0)


# ---------------------------------------------------------------------------
# 测试：初始状态
# ---------------------------------------------------------------------------

class TestParametersInit:
    """验证 _parameters 在模块初始化后的初始状态。"""

    def test_exists_after_init(self):
        """_parameters 在 __init__ 后即存在。"""
        m = nn.Module()
        assert hasattr(m, "_parameters")

    def test_is_dict(self):
        """_parameters 是 dict 类型（Python 3.7+ 下 PyTorch 使用普通 dict）。"""
        m = nn.Module()
        assert isinstance(m._parameters, dict)

    def test_empty_for_plain_module(self):
        """空模块的 _parameters 不含任何键。"""
        m = nn.Module()
        assert len(m._parameters) == 0


# ---------------------------------------------------------------------------
# 测试：register_parameter
# ---------------------------------------------------------------------------

class TestRegisterParameter:
    """通过 register_parameter 注册参数后验证 _parameters 内容。"""

    def test_register_parameter_appears_in_dict(self):
        """register_parameter 后参数出现在 _parameters 中。"""
        npu = _npu_device()
        m = nn.Module()
        param = nn.Parameter(torch.randn(4, 4, device=npu))
        m.register_parameter("weight", param)
        assert "weight" in m._parameters
        assert m._parameters["weight"] is param

    def test_register_parameter_none_key_exists(self):
        """register_parameter(name, None) 后键存在，值为 None。"""
        m = nn.Module()
        m.register_parameter("bias", None)
        assert "bias" in m._parameters
        assert m._parameters["bias"] is None

    def test_register_multiple_parameters(self):
        """注册多个参数后，_parameters 中均可查到。"""
        npu = _npu_device()
        m = nn.Module()
        w = nn.Parameter(torch.randn(3, 3, device=npu))
        b = nn.Parameter(torch.randn(3, device=npu))
        m.register_parameter("weight", w)
        m.register_parameter("bias", b)
        assert "weight" in m._parameters
        assert "bias" in m._parameters
        assert len(m._parameters) == 2

    def test_overwrite_parameter(self):
        """同名参数被覆盖后，_parameters 中保存新参数。"""
        npu = _npu_device()
        m = nn.Module()
        p1 = nn.Parameter(torch.randn(2, device=npu))
        p2 = nn.Parameter(torch.randn(4, device=npu))
        m.register_parameter("weight", p1)
        m.register_parameter("weight", p2)
        assert m._parameters["weight"] is p2
        assert len(m._parameters) == 1


# ---------------------------------------------------------------------------
# 测试：直接属性赋值
# ---------------------------------------------------------------------------

class TestAttributeAssignment:
    """通过属性赋值方式添加 nn.Parameter 时，验证 _parameters 填充行为。"""

    def test_assign_parameter_attribute(self):
        """直接赋值 self.attr = nn.Parameter(...) 后出现在 _parameters。"""
        npu = _npu_device()

        class SimpleModule(nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = nn.Parameter(torch.randn(5, 5, device=npu))

        m = SimpleModule()
        assert "weight" in m._parameters
        assert isinstance(m._parameters["weight"], nn.Parameter)


# ---------------------------------------------------------------------------
# 测试：NPU 设备行为
# ---------------------------------------------------------------------------

class TestNpuDevice:
    """验证存储在 _parameters 中的参数位于正确的 NPU 设备。"""

    def test_parameter_device_is_npu(self):
        """在 NPU 上创建的参数，其 device.type 应为 'npu'。"""
        npu = _npu_device()
        m = nn.Module()
        param = nn.Parameter(torch.randn(3, 3, device=npu))
        m.register_parameter("weight", param)
        stored = m._parameters["weight"]
        assert stored.device.type == "npu"

    def test_parameter_index_is_zero(self):
        """NPU 参数的 device index 应为 0（单卡场景）。"""
        npu = _npu_device()
        m = nn.Module()
        param = nn.Parameter(torch.randn(2, 2, device=npu))
        m.register_parameter("w", param)
        assert m._parameters["w"].device == torch.device("npu", 0)


# ---------------------------------------------------------------------------
# 测试：nn.Linear 内置模块的 _parameters
# ---------------------------------------------------------------------------

class TestBuiltinModule:
    """使用 nn.Linear 验证内置模块的 _parameters 行为。"""

    def test_linear_has_weight_and_bias(self):
        """nn.Linear 的 _parameters 包含 weight 和 bias。"""
        npu = _npu_device()
        m = nn.Linear(4, 8).to(npu)
        assert "weight" in m._parameters
        assert "bias" in m._parameters

    def test_linear_weight_is_parameter(self):
        """nn.Linear 的 weight 是 nn.Parameter 实例。"""
        npu = _npu_device()
        m = nn.Linear(4, 8).to(npu)
        assert isinstance(m._parameters["weight"], nn.Parameter)

    def test_linear_weight_device_is_npu(self):
        """nn.Linear to(npu) 后，weight 的 device.type 为 'npu'。"""
        npu = _npu_device()
        m = nn.Linear(4, 8).to(npu)
        assert m._parameters["weight"].device.type == "npu"

    def test_linear_no_bias(self):
        """nn.Linear(bias=False) 时，_parameters 中 bias 键存在但值为 None。"""
        npu = _npu_device()
        m = nn.Linear(4, 8, bias=False).to(npu)
        # bias=False 时，PyTorch 仍通过 __setattr__ 将 bias=None 注册进 _parameters
        assert "weight" in m._parameters
        assert "bias" in m._parameters
        assert m._parameters["bias"] is None

    def test_linear_parameters_count_with_bias(self):
        """nn.Linear(bias=True) 时，_parameters 恰好有 2 个条目。"""
        npu = _npu_device()
        m = nn.Linear(4, 8, bias=True).to(npu)
        assert len(m._parameters) == 2


# ---------------------------------------------------------------------------
# 测试：OrderedDict 顺序保持
# ---------------------------------------------------------------------------

class TestOrdering:
    """验证 _parameters 保持注册顺序。"""

    def test_insertion_order_preserved(self):
        """_parameters 以注册顺序返回键名。"""
        npu = _npu_device()
        m = nn.Module()
        names = ["alpha", "beta", "gamma"]
        for name in names:
            m.register_parameter(name, nn.Parameter(torch.randn(2, device=npu)))
        assert list(m._parameters.keys()) == names
