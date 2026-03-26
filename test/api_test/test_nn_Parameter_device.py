# 测试目的：验证 torch.nn.Parameter.device 属性在 NPU 上的正确行为
# API 名称：torch.nn.Parameter.device（继承自 torch.Tensor.device）
#
# 覆盖维度：
# | 覆盖维度              | 说明                                          | 覆盖情况                          |
# |----------------------|-----------------------------------------------|-----------------------------------|
# | 空/非空（None 或其他）| Parameter(data=None) 与 data 为具体 Tensor   | 已覆盖：test_device_cpu_default、test_device_from_tensor |
# | 枚举选项              | device 类型为 'cpu' / 'npu'                  | 已覆盖：多个测试用例              |
# | 参数类型              | data 为 1D/2D Tensor、不同 dtype             | 已覆盖：float32、float16、int64   |
# | 传参与不传参          | Parameter(data=None) vs Parameter(data=Tensor)| 已覆盖                            |
# | 等价类/边界值         | 标量、1D、2D Tensor；CPU→NPU 迁移            | 已覆盖                            |
# | 正常传参场景          | CPU 创建、NPU 创建、.to(npu)、Module.to(npu) | 已覆盖：多个正常路径测试          |
# | 异常传参场景          | N/A（device 为只读属性，无异常路径可测试）    | N/A                               |
#
# 代码分支覆盖分析：
# 1. data=None → 内部创建空 CPU Tensor，device.type == 'cpu'    → test_device_cpu_default
# 2. type(data) is torch.Tensor（CPU）→ _make_subclass，device 继承自 data（cpu）
#                                                                → test_device_from_cpu_tensor
# 3. type(data) is torch.Tensor（NPU）→ _make_subclass，device 继承自 data（npu）
#                                                                → test_device_from_npu_tensor
# 4. .to(device) 迁移 CPU→NPU → device 变为 npu               → test_device_after_to_npu
# 5. nn.Module.to(npu) → 模块所有 Parameter device 变 npu      → test_module_parameter_device_after_to_npu
# 6. Parameter 参与加法运算 → 结果 Tensor device 跟随           → test_device_of_computation_result
# 7. 不同 dtype 的 Parameter 在 NPU 上 device 属性一致         → test_device_various_dtypes_on_npu
# 8. requires_grad=False 时 device 行为不变                     → test_device_requires_grad_false
#
# 未覆盖项：
# - 自定义 Tensor 类型路径（_is_param 标记路径）：需要自定义 __torch_dispatch__，实现复杂且
#   非主流使用场景，与 device 属性本身无关，不做覆盖。
# - UninitializedParameter.device：device 属性在未初始化参数上可访问，但与主 API 无直接关联。

import pytest
import torch
import torch.nn as nn
import torch_npu  # noqa: F401


def npu_device():
    """返回 NPU 设备对象，若 NPU 不可用则跳过。"""
    if not torch.npu.is_available():
        pytest.skip("NPU 设备不可用")
    return torch.device("npu", 0)


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
# 分支 2/3：在 NPU 上直接创建 Parameter（type(data) is torch.Tensor，data 在 NPU）
# ---------------------------------------------------------------------------
class TestParameterDeviceNpuDirect:
    def test_device_from_npu_tensor(self):
        """直接用 NPU Tensor 创建的 Parameter，device.type 为 'npu'。"""
        dev = npu_device()
        data = torch.randn(3, 4, device=dev)
        param = nn.Parameter(data)
        assert isinstance(param.device, torch.device)
        assert param.device.type == "npu"

    def test_device_index_is_int(self):
        """NPU Parameter 的 device.index 为整数。"""
        dev = npu_device()
        data = torch.randn(2, 2, device=dev)
        param = nn.Parameter(data)
        assert param.device.type == "npu"
        assert isinstance(param.device.index, int)

    def test_device_index_is_zero(self):
        """默认 NPU 设备的 device.index 为 0。"""
        dev = npu_device()
        data = torch.randn(5, device=dev)
        param = nn.Parameter(data)
        assert param.device == torch.device("npu", 0)

    def test_device_return_type_on_npu(self):
        """NPU Parameter 的 device 返回类型为 torch.device。"""
        dev = npu_device()
        param = nn.Parameter(torch.randn(3, device=dev))
        assert type(param.device) is torch.device


# ---------------------------------------------------------------------------
# 分支 4：CPU → NPU 迁移（.to(npu)）
# ---------------------------------------------------------------------------
class TestParameterDeviceToNpu:
    def test_device_after_to_npu(self):
        """CPU Parameter 经 .to(npu) 后 device.type 变为 'npu'。"""
        dev = npu_device()
        param = nn.Parameter(torch.randn(3, 4))
        assert param.device.type == "cpu"
        param_npu = param.to(dev)
        assert param_npu.device.type == "npu"

    def test_device_after_to_npu_string(self):
        """CPU Parameter 经 .to('npu') 后 device.type 变为 'npu'。"""
        npu_device()  # 确保 NPU 可用
        param = nn.Parameter(torch.randn(6))
        param_npu = param.to("npu")
        assert param_npu.device.type == "npu"

    def test_device_after_to_npu_with_index(self):
        """CPU Parameter 经 .to(torch.device('npu', 0)) 后 device 等于 npu:0。"""
        dev = npu_device()
        param = nn.Parameter(torch.randn(2, 3))
        param_npu = param.to(dev)
        assert param_npu.device == torch.device("npu", 0)

    def test_original_param_device_unchanged_after_to(self):
        """调用 .to(npu) 后原始 CPU Parameter 的 device 不变。"""
        npu_device()
        param = nn.Parameter(torch.randn(4, 4))
        _ = param.to("npu")
        # .to() 不做 in-place 操作，原始 param 仍在 CPU
        assert param.device.type == "cpu"


# ---------------------------------------------------------------------------
# 分支 5：nn.Module.to(npu) 后模块内参数 device
# ---------------------------------------------------------------------------
class TestModuleParameterDeviceToNpu:
    def test_module_parameter_device_after_to_npu(self):
        """nn.Module.to(npu) 后，模块内所有 Parameter device.type 为 'npu'。"""
        dev = npu_device()
        model = nn.Linear(4, 4)
        assert model.weight.device.type == "cpu"
        model = model.to(dev)
        assert model.weight.device.type == "npu"
        assert model.bias.device.type == "npu"

    def test_nested_module_parameter_device_after_to_npu(self):
        """嵌套 Module.to(npu) 后，各层 Parameter device 均为 'npu'。"""
        dev = npu_device()
        model = nn.Sequential(nn.Linear(8, 8), nn.Linear(8, 4))
        model = model.to(dev)
        for name, param in model.named_parameters():
            assert param.device.type == "npu", f"{name}.device.type 应为 npu"

    def test_named_parameters_device_on_npu(self):
        """named_parameters() 遍历的每个参数 device.type 为 'npu'。"""
        dev = npu_device()
        model = nn.Linear(3, 3).to(dev)
        for name, param in model.named_parameters():
            assert param.device.type == "npu"
            assert isinstance(param.device, torch.device)

    def test_module_parameter_device_index_on_npu(self):
        """Module.to(npu) 后参数 device.index 为 0（默认 NPU）。"""
        dev = npu_device()
        model = nn.Linear(2, 2).to(dev)
        assert model.weight.device.index == 0


# ---------------------------------------------------------------------------
# 分支 6：Parameter 参与运算，结果 device 跟随输入
# ---------------------------------------------------------------------------
class TestParameterComputationResultDevice:
    def test_device_of_computation_result(self):
        """两个 NPU Parameter 相加，结果 Tensor 的 device.type 为 'npu'。"""
        dev = npu_device()
        p1 = nn.Parameter(torch.randn(3, 3, device=dev))
        p2 = nn.Parameter(torch.randn(3, 3, device=dev))
        result = p1 + p2
        assert result.device.type == "npu"

    def test_device_of_matmul_result(self):
        """NPU Parameter 矩阵乘法结果的 device.type 为 'npu'。"""
        dev = npu_device()
        p = nn.Parameter(torch.randn(4, 4, device=dev))
        x = torch.randn(4, 4, device=dev)
        result = torch.matmul(p, x)
        assert result.device.type == "npu"

    def test_device_of_sum_result(self):
        """NPU Parameter.sum() 结果的 device.type 为 'npu'。"""
        dev = npu_device()
        p = nn.Parameter(torch.randn(5, device=dev))
        result = p.sum()
        assert result.device.type == "npu"


# ---------------------------------------------------------------------------
# 分支 7：不同 dtype 的 Parameter 在 NPU 上 device 属性一致
# ---------------------------------------------------------------------------
class TestParameterDeviceVariousDtypes:
    def test_device_float32_npu(self):
        """float32 类型 NPU Parameter 的 device.type 为 'npu'。"""
        dev = npu_device()
        param = nn.Parameter(torch.randn(4, dtype=torch.float32, device=dev))
        assert param.device.type == "npu"

    def test_device_float16_npu(self):
        """float16 类型 NPU Parameter 的 device.type 为 'npu'。"""
        dev = npu_device()
        param = nn.Parameter(torch.randn(4, dtype=torch.float16, device=dev))
        assert param.device.type == "npu"

    def test_device_int64_npu_no_grad(self):
        """int64 类型（requires_grad=False）NPU Parameter 的 device.type 为 'npu'。"""
        dev = npu_device()
        # 整数类型不支持 requires_grad=True，须显式指定 False
        param = nn.Parameter(
            torch.randint(0, 10, (4,), device=dev).to(torch.int64),
            requires_grad=False,
        )
        assert param.device.type == "npu"


# ---------------------------------------------------------------------------
# 分支 8：requires_grad=False 时 device 行为不变
# ---------------------------------------------------------------------------
class TestParameterDeviceRequiresGrad:
    def test_device_requires_grad_true_npu(self):
        """requires_grad=True 时 NPU Parameter 的 device.type 为 'npu'。"""
        dev = npu_device()
        param = nn.Parameter(torch.randn(3, device=dev), requires_grad=True)
        assert param.device.type == "npu"

    def test_device_requires_grad_false_npu(self):
        """requires_grad=False 时 NPU Parameter 的 device.type 仍为 'npu'。"""
        dev = npu_device()
        param = nn.Parameter(torch.randn(3, device=dev), requires_grad=False)
        assert param.device.type == "npu"

    def test_device_requires_grad_false_cpu(self):
        """requires_grad=False 时 CPU Parameter 的 device.type 为 'cpu'。"""
        param = nn.Parameter(torch.randn(3), requires_grad=False)
        assert param.device.type == "cpu"
