# 测试目的：验证 torch.nn.Module.__setattr__ 在加速卡（NPU/GPU）环境下的功能行为与接口覆盖
# API 名称：torch.nn.Module.__setattr__
#
# 覆盖参数维度：
#
# | 覆盖维度             | 说明                                                                  | 覆盖情况                                                                      |
# |----------------------|-----------------------------------------------------------------------|-------------------------------------------------------------------------------|
# | 空/非空（None/非None）| value 为 None（注销已有 Parameter/Module/Buffer）、非 None            | 覆盖：参数注销、模块注销、Buffer 注销（None）、各类非 None 赋值               |
# | 枚举选项             | value 的类型：Parameter、Module、Buffer、Tensor、int、str             | 覆盖：全部主要类型（含 Buffer 分支）                                          |
# | 参数类型             | name 为字符串；value 为 Parameter/Module/Buffer/Tensor/int/str/float  | 覆盖：Parameter、Module、Buffer（persistent/non-persistent）、Tensor、标量    |
# | 传参与不传参         | N/A（__setattr__ 参数固定）                                           | N/A                                                                           |
# | 等价类/边界值        | 初次赋值、覆盖已有参数/模块/Buffer（None/同类型新值）                 | 覆盖：首次赋值、覆盖为 None、覆盖为新值、Tensor 覆盖已有 Buffer 槽           |
# | 正常传参场景         | 合法输入下 API 可正常调用                                             | 覆盖：参数/模块/Buffer/张量/标量赋值均可正常运行                              |
# | 异常传参场景         | 已有 param 槽赋非 Param 非 None → TypeError；module 槽同理；buffer 同 | 覆盖：三种槽位的 TypeError 均使用 pytest.raises 验证                          |
#
# 未覆盖项：
# - Module.__init__() 调用前赋值（AttributeError）：构造条件繁琐且非常规使用路径，省略
# - 复数 dtype 的 Parameter：与主要功能场景等价，省略

import pytest
import torch
import torch.nn as nn


# ---------------------------------------------------------------------------
# 辅助模块
# ---------------------------------------------------------------------------

class SimpleModule(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, x):
        return x


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestSetAttrParameter:
    """测试将 nn.Parameter 赋值给模块属性，应注册到 _parameters。"""

    def test_set_parameter_registers_in_parameters(self, device):
        model = SimpleModule().to(device)
        param = nn.Parameter(torch.randn(3, 4, device=device))
        model.weight = param
        assert "weight" in model._parameters
        assert model._parameters["weight"] is param

    def test_set_parameter_not_in_modules_or_buffers(self, device):
        model = SimpleModule().to(device)
        param = nn.Parameter(torch.randn(2, 2, device=device))
        model.my_param = param
        assert "my_param" not in model._modules
        assert "my_param" not in model._buffers

    def test_set_parameter_device_type(self, device):
        model = SimpleModule().to(device)
        param = nn.Parameter(torch.randn(5, device=device))
        model.acc_param = param
        assert model._parameters["acc_param"].device.type == device.type

    def test_overwrite_parameter_with_none_deregisters(self, device):
        """将已注册的 Parameter 槽位置 None 应注销该参数。"""
        model = SimpleModule().to(device)
        param = nn.Parameter(torch.randn(3, device=device))
        model.weight = param
        assert "weight" in model._parameters
        model.weight = None
        assert "weight" in model._parameters
        assert model._parameters["weight"] is None

    def test_overwrite_parameter_with_new_parameter(self, device):
        """将已注册的 Parameter 槽位替换为新 Parameter。"""
        model = SimpleModule().to(device)
        param1 = nn.Parameter(torch.randn(3, device=device))
        model.weight = param1
        param2 = nn.Parameter(torch.randn(3, device=device))
        model.weight = param2
        assert model._parameters["weight"] is param2


class TestSetAttrModule:
    """测试将 nn.Module 赋值给属性，应注册到 _modules。"""

    def test_set_submodule_registers_in_modules(self, device):
        model = SimpleModule().to(device)
        sub = SimpleModule().to(device)
        model.sub = sub
        assert "sub" in model._modules
        assert model._modules["sub"] is sub

    def test_set_submodule_not_in_parameters_or_buffers(self, device):
        model = SimpleModule().to(device)
        sub = SimpleModule().to(device)
        model.encoder = sub
        assert "encoder" not in model._parameters
        assert "encoder" not in model._buffers

    def test_overwrite_module_with_new_module(self, device):
        """将已注册的子模块替换为新模块。"""
        model = SimpleModule().to(device)
        sub1 = SimpleModule().to(device)
        sub2 = SimpleModule().to(device)
        model.sub = sub1
        model.sub = sub2
        assert model._modules["sub"] is sub2

    def test_overwrite_module_with_none_deregisters(self, device):
        """将已注册的子模块槽位置 None 应注销该模块。"""
        model = SimpleModule().to(device)
        sub = SimpleModule().to(device)
        model.sub = sub
        model.sub = None
        assert "sub" in model._modules
        assert model._modules["sub"] is None


class TestSetAttrBuffer:
    """测试将 nn.Buffer 或 Tensor 赋值到 buffer 槽位，应注册到 _buffers。"""

    def test_set_buffer_registers_in_buffers(self, device):
        """nn.Buffer 赋值后应出现在 _buffers 中。"""
        model = SimpleModule()
        buf = nn.Buffer(torch.randn(4, device=device))
        model.my_buf = buf
        assert "my_buf" in model._buffers
        assert model._buffers["my_buf"].device.type == device.type

    def test_set_buffer_not_in_parameters_or_modules(self, device):
        """nn.Buffer 赋值后不应出现在 _parameters 或 _modules 中。"""
        model = SimpleModule()
        buf = nn.Buffer(torch.randn(3, device=device))
        model.my_buf = buf
        assert "my_buf" not in model._parameters
        assert "my_buf" not in model._modules

    def test_set_buffer_persistent_default(self, device):
        """nn.Buffer 默认 persistent=True，不应出现在 _non_persistent_buffers_set。"""
        model = SimpleModule()
        buf = nn.Buffer(torch.randn(3, device=device))
        model.p_buf = buf
        assert "p_buf" not in model._non_persistent_buffers_set

    def test_set_buffer_non_persistent(self, device):
        """nn.Buffer(persistent=False) 应注册为非持久 buffer。"""
        model = SimpleModule()
        buf = nn.Buffer(torch.randn(3, device=device), persistent=False)
        model.np_buf = buf
        assert "np_buf" in model._buffers
        assert "np_buf" in model._non_persistent_buffers_set

    def test_register_buffer_then_overwrite_with_tensor(self, device):
        """register_buffer 后使用普通 Tensor 覆盖写，应保留在 _buffers 中。"""
        model = SimpleModule()
        model.register_buffer("feat", torch.randn(3))
        model.feat = torch.randn(3, device=device)
        assert "feat" in model._buffers
        assert model._buffers["feat"].device.type == device.type

    def test_register_buffer_then_overwrite_with_none(self, device):
        """已有 buffer 槽位覆盖为 None，键保留但值为 None。"""
        model = SimpleModule()
        model.register_buffer("feat", torch.randn(3, device=device))
        model.feat = None
        assert "feat" in model._buffers
        assert model._buffers["feat"] is None

    def test_overwrite_buffer_slot_with_non_tensor_non_none_raises_typeerror(self, device):
        """已有 buffer 槽赋非 Tensor 非 None 值时，源码明确抛出 TypeError。"""
        model = SimpleModule()
        model.register_buffer("feat", torch.randn(3, device=device))
        with pytest.raises(TypeError):
            model.feat = 42


class TestSetAttrPlainTensor:
    """测试将普通 Tensor（非 Parameter）赋值，应进入普通 __dict__，不注册为 Parameter。"""

    def test_set_plain_tensor_not_in_parameters(self, device):
        model = SimpleModule().to(device)
        t = torch.randn(3, 4, device=device)
        model.feat = t
        assert "feat" not in model._parameters
        assert "feat" not in model._modules

    def test_set_plain_tensor_accessible_as_attr(self, device):
        model = SimpleModule().to(device)
        t = torch.randn(2, 2, device=device)
        model.data_tensor = t
        assert model.data_tensor is t


class TestSetAttrPythonScalars:
    """测试将普通 Python 值（int、str、float）赋值。"""

    def test_set_int_attr(self, device):
        model = SimpleModule().to(device)
        model.num_classes = 10
        assert model.num_classes == 10
        assert "num_classes" not in model._parameters
        assert "num_classes" not in model._modules

    def test_set_str_attr(self, device):
        model = SimpleModule().to(device)
        model.name_tag = "encoder"
        assert model.name_tag == "encoder"

    def test_set_float_attr(self, device):
        model = SimpleModule().to(device)
        model.dropout_rate = 0.5
        assert model.dropout_rate == 0.5


class TestSetAttrExceptions:
    """测试源码中明确记录的异常行为。"""

    def test_overwrite_param_slot_with_non_param_non_none_raises_typeerror(self, device):
        """已注册参数槽位赋非 Parameter、非 None 值时，源码明确抛出 TypeError。"""
        model = SimpleModule().to(device)
        param = nn.Parameter(torch.randn(3, device=device))
        model.weight = param
        plain_tensor = torch.randn(3, device=device)
        with pytest.raises(TypeError):
            model.weight = plain_tensor

    def test_overwrite_module_slot_with_non_module_non_none_raises_typeerror(self, device):
        """已注册子模块槽位赋非 Module、非 None 值时，源码明确抛出 TypeError。"""
        model = SimpleModule().to(device)
        model.sub = SimpleModule().to(device)
        with pytest.raises(TypeError):
            model.sub = 42


class TestSetAttrSubclassOverride:
    """测试在子类中覆盖 __setattr__ 并调用 super()，验证兼容性。"""

    def test_subclass_override_with_super_call(self, device):
        """子类覆盖 __setattr__，在调用 super 前添加前缀，功能行为应与标准一致。"""

        class PrefixedModule(nn.Module):
            def __init__(self):
                super().__init__()

            def __setattr__(self, key, value):
                if isinstance(value, nn.Parameter):
                    super().__setattr__(f"pfx_{key}", value)
                else:
                    super().__setattr__(key, value)

            def forward(self, x):
                return x

        model = PrefixedModule().to(device)
        param = nn.Parameter(torch.randn(4, device=device))
        model.weight = param
        assert "pfx_weight" in model._parameters
        assert model._parameters["pfx_weight"] is param

    def test_subclass_passthrough_setattr(self, device):
        """子类直接透传 __setattr__ 到 super()，行为与基类相同。"""

        class PassthroughModule(nn.Module):
            def __init__(self):
                super().__init__()

            def __setattr__(self, key, value):
                super().__setattr__(key, value)

            def forward(self, x):
                return x

        model = PassthroughModule().to(device)
        param = nn.Parameter(torch.randn(3, device=device))
        model.linear_weight = param
        assert "linear_weight" in model._parameters

        sub = SimpleModule().to(device)
        model.sub = sub
        assert "sub" in model._modules
