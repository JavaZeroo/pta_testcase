# 测试目的：验证 torch.nn.Parameter.device 属性在加速卡（NPU/GPU）上的正确行为
# API 名称：torch.nn.Parameter.device（继承自 torch.Tensor.device）
#
# 覆盖维度：
# | 覆盖维度              | 说明                                          | 覆盖情况                          |
# |----------------------|-----------------------------------------------|-----------------------------------|
# | 空/非空（None 或其他）| Parameter(data=None) 与 data 为具体 Tensor   | 已覆盖                            |
# | 枚举选项              | device 类型为 'cpu' / 加速卡后端             | 已覆盖：多个测试用例              |
# | 参数类型              | data 为 1D/2D Tensor、不同 dtype             | 已覆盖：float32、float16、int64   |
# | 传参与不传参          | Parameter(data=None) vs Parameter(data=Tensor)| 已覆盖                            |
# | 等价类/边界值         | 标量、1D、2D Tensor；CPU→加速卡迁移           | 已覆盖                            |
# | 正常传参场景          | CPU 创建、加速卡创建、.to(device)、Module.to  | 已覆盖：多个正常路径测试          |
# | 异常传参场景          | N/A（device 为只读属性，无异常路径可测试）    | N/A                               |
#
# 未覆盖项：
# - 自定义 Tensor 类型路径（_is_param 标记路径）：需要自定义 __torch_dispatch__，实现复杂且
#   非主流使用场景，与 device 属性本身无关，不做覆盖。
# - UninitializedParameter.device：device 属性在未初始化参数上可访问，但与主 API 无直接关联。

import pytest
import torch
import torch.nn as nn


# ---------------------------------------------------------------------------
# 分支 1：data=None，内部创建空 CPU Tensor
# ---------------------------------------------------------------------------
class TestParameterDeviceCpuDefault:
    def test_device_cpu_default(self):
        """Parameter(data=None) 默认在 CPU 上创建，device.type 为 'cpu'。"""
        param = nn.Parameter()
        assert isinstance(param.device, torch.device)
        assert param.device.type == "cpu"

    def test_device_from_cpu_tensor(self):
        """用 CPU Tensor 创建的 Parameter，device.type 为 'cpu'。"""
        data = torch.randn(3, 4)
        param = nn.Parameter(data)
        assert isinstance(param.device, torch.device)
        assert param.device.type == "cpu"

    def test_device_scalar_cpu(self):
        """标量 CPU Tensor 的 Parameter，device.type 为 'cpu'。"""
        param = nn.Parameter(torch.tensor(1.0))
        assert param.device.type == "cpu"

    def test_device_1d_cpu(self):
        """1D CPU Tensor 的 Parameter，device.type 为 'cpu'。"""
        param = nn.Parameter(torch.randn(10))
        assert param.device.type == "cpu"

    def test_device_2d_cpu(self):
        """2D CPU Tensor 的 Parameter，device.type 为 'cpu'。"""
        param = nn.Parameter(torch.randn(4, 8))
        assert param.device.type == "cpu"


# ---------------------------------------------------------------------------
# 分支 2/3：在加速卡上直接创建 Parameter
# ---------------------------------------------------------------------------
class TestParameterDeviceAcceleratorDirect:
    def test_device_from_accelerator_tensor(self, device):
        """直接用加速卡 Tensor 创建的 Parameter，device.type 与后端一致。"""
        data = torch.randn(3, 4, device=device)
        param = nn.Parameter(data)
        assert isinstance(param.device, torch.device)
        assert param.device.type == device.type

    def test_device_index_is_int(self, device):
        """加速卡 Parameter 的 device.index 为整数。"""
        data = torch.randn(2, 2, device=device)
        param = nn.Parameter(data)
        assert param.device.type == device.type
        assert isinstance(param.device.index, int)

    def test_device_index_is_zero(self, device):
        """默认加速卡设备的 device.index 为 0。"""
        data = torch.randn(5, device=device)
        param = nn.Parameter(data)
        assert param.device == device

    def test_device_return_type_on_accelerator(self, device):
        """加速卡 Parameter 的 device 返回类型为 torch.device。"""
        param = nn.Parameter(torch.randn(3, device=device))
        assert type(param.device) is torch.device


# ---------------------------------------------------------------------------
# 分支 4：CPU → 加速卡迁移（.to(device)）
# ---------------------------------------------------------------------------
class TestParameterDeviceToAccelerator:
    def test_device_after_to_accelerator(self, device):
        """CPU Parameter 经 .to(device) 后 device.type 变为加速卡后端。"""
        param = nn.Parameter(torch.randn(3, 4))
        assert param.device.type == "cpu"
        param_acc = param.to(device)
        assert param_acc.device.type == device.type

    def test_device_after_to_accelerator_string(self, device_name, device):
        """CPU Parameter 经 .to(device_name) 后 device.type 正确。"""
        param = nn.Parameter(torch.randn(6))
        param_acc = param.to(device_name)
        assert param_acc.device.type == device.type

    def test_device_after_to_accelerator_with_index(self, device):
        """CPU Parameter 经 .to(device) 后 device 等于目标 device。"""
        param = nn.Parameter(torch.randn(2, 3))
        param_acc = param.to(device)
        assert param_acc.device == device

    def test_original_param_device_unchanged_after_to(self, device_name):
        """调用 .to(device) 后原始 CPU Parameter 的 device 不变。"""
        param = nn.Parameter(torch.randn(4, 4))
        _ = param.to(device_name)
        assert param.device.type == "cpu"


# ---------------------------------------------------------------------------
# 分支 5：nn.Module.to(device) 后模块内参数 device
# ---------------------------------------------------------------------------
class TestModuleParameterDeviceToAccelerator:
    def test_module_parameter_device_after_to(self, device):
        """nn.Module.to(device) 后，模块内所有 Parameter device.type 正确。"""
        model = nn.Linear(4, 4)
        assert model.weight.device.type == "cpu"
        model = model.to(device)
        assert model.weight.device.type == device.type
        assert model.bias.device.type == device.type

    def test_nested_module_parameter_device_after_to(self, device):
        """嵌套 Module.to(device) 后，各层 Parameter device 均正确。"""
        model = nn.Sequential(nn.Linear(8, 8), nn.Linear(8, 4))
        model = model.to(device)
        for name, param in model.named_parameters():
            assert param.device.type == device.type, f"{name}.device.type 应为 {device.type}"

    def test_named_parameters_device_on_accelerator(self, device):
        """named_parameters() 遍历的每个参数 device.type 与后端一致。"""
        model = nn.Linear(3, 3).to(device)
        for name, param in model.named_parameters():
            assert param.device.type == device.type
            assert isinstance(param.device, torch.device)

    def test_module_parameter_device_index(self, device):
        """Module.to(device) 后参数 device.index 为 0（默认）。"""
        model = nn.Linear(2, 2).to(device)
        assert model.weight.device.index == 0


# ---------------------------------------------------------------------------
# 分支 6：Parameter 参与运算，结果 device 跟随输入
# ---------------------------------------------------------------------------
class TestParameterComputationResultDevice:
    def test_device_of_computation_result(self, device):
        """两个加速卡 Parameter 相加，结果 Tensor 的 device.type 正确。"""
        p1 = nn.Parameter(torch.randn(3, 3, device=device))
        p2 = nn.Parameter(torch.randn(3, 3, device=device))
        result = p1 + p2
        assert result.device.type == device.type

    def test_device_of_matmul_result(self, device):
        """加速卡 Parameter 矩阵乘法结果的 device.type 正确。"""
        p = nn.Parameter(torch.randn(4, 4, device=device))
        x = torch.randn(4, 4, device=device)
        result = torch.matmul(p, x)
        assert result.device.type == device.type

    def test_device_of_sum_result(self, device):
        """加速卡 Parameter.sum() 结果的 device.type 正确。"""
        p = nn.Parameter(torch.randn(5, device=device))
        result = p.sum()
        assert result.device.type == device.type


# ---------------------------------------------------------------------------
# 分支 7：不同 dtype 的 Parameter 在加速卡上 device 属性一致
# ---------------------------------------------------------------------------
class TestParameterDeviceVariousDtypes:
    def test_device_float32(self, device):
        """float32 类型加速卡 Parameter 的 device.type 正确。"""
        param = nn.Parameter(torch.randn(4, dtype=torch.float32, device=device))
        assert param.device.type == device.type

    def test_device_float16(self, device):
        """float16 类型加速卡 Parameter 的 device.type 正确。"""
        param = nn.Parameter(torch.randn(4, dtype=torch.float16, device=device))
        assert param.device.type == device.type

    def test_device_int64_no_grad(self, device):
        """int64 类型（requires_grad=False）加速卡 Parameter 的 device.type 正确。"""
        param = nn.Parameter(
            torch.randint(0, 10, (4,), device=device).to(torch.int64),
            requires_grad=False,
        )
        assert param.device.type == device.type


# ---------------------------------------------------------------------------
# 分支 8：requires_grad=False 时 device 行为不变
# ---------------------------------------------------------------------------
class TestParameterDeviceRequiresGrad:
    def test_device_requires_grad_true(self, device):
        """requires_grad=True 时加速卡 Parameter 的 device.type 正确。"""
        param = nn.Parameter(torch.randn(3, device=device), requires_grad=True)
        assert param.device.type == device.type

    def test_device_requires_grad_false(self, device):
        """requires_grad=False 时加速卡 Parameter 的 device.type 仍正确。"""
        param = nn.Parameter(torch.randn(3, device=device), requires_grad=False)
        assert param.device.type == device.type

    def test_device_requires_grad_false_cpu(self):
        """requires_grad=False 时 CPU Parameter 的 device.type 为 'cpu'。"""
        param = nn.Parameter(torch.randn(3), requires_grad=False)
        assert param.device.type == "cpu"
