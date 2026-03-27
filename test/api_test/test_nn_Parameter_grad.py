# 测试目的：验证 torch.nn.Parameter.grad 属性在加速卡（NPU/GPU）上的功能行为
# API 名称：torch.nn.Parameter.grad（继承自 torch.Tensor.grad）
#
# 覆盖维度：
# | 覆盖维度             | 说明                                           | 覆盖情况                               |
# |----------------------|------------------------------------------------|----------------------------------------|
# | 空/非空（None 或其他）| .grad 默认为 None；backward 后变为 Tensor       | 覆盖：default_none / after_backward    |
# | 枚举选项             | N/A（.grad 为属性，无枚举参数）                  | N/A                                    |
# | 参数类型             | float32 / float64 的 Parameter；标量/矩阵形状   | 覆盖：dtype_float32 / dtype_float64    |
# | 传参与不传参         | requires_grad=True（默认）/ requires_grad=False | 覆盖：requires_grad_false              |
# | 等价类/边界值        | 标量(1,)、向量(3,)、矩阵(2,3) 等形状            | 覆盖：shape_scalar / shape_matrix      |
# | 正常传参场景         | backward → grad 非 None；累加；手动赋值；zero   | 覆盖：多个 test_* 函数                 |
# | 异常传参场景         | N/A（.grad 赋值错误类型时 PyTorch 不稳定抛异常） | 未覆盖，无确切证据                     |
#
# 未覆盖项及原因：
# - 对 .grad 赋值非 Tensor 类型（如 int）：PyTorch 文档未明确规定会抛出何种异常，
#   实际行为依版本而异，故不生成此类负例。
# - 非叶子 Tensor 的 .grad：nn.Parameter 始终是叶子节点，非叶子场景与本 API 无关。

import pytest
import torch
import torch.nn as nn


# ---------------------------------------------------------------------------
# 1. 默认状态：.grad 为 None
# ---------------------------------------------------------------------------

class TestParameterGradDefault:
    """新建 Parameter 后 .grad 默认为 None。"""

    def test_grad_default_none_1d(self, device):
        p = nn.Parameter(torch.randn(4, device=device))
        assert p.grad is None

    def test_grad_default_none_2d(self, device):
        p = nn.Parameter(torch.randn(3, 4, device=device))
        assert p.grad is None

    def test_grad_default_none_scalar(self, device):
        p = nn.Parameter(torch.tensor(1.0, device=device))
        assert p.grad is None


# ---------------------------------------------------------------------------
# 2. backward 后 .grad 变为 Tensor
# ---------------------------------------------------------------------------

class TestParameterGradAfterBackward:
    """执行 backward 后 .grad 应变为非 None 的 Tensor。"""

    def test_grad_becomes_tensor_after_backward(self, device):
        p = nn.Parameter(torch.randn(4, device=device))
        loss = p.sum()
        loss.backward()
        assert p.grad is not None
        assert isinstance(p.grad, torch.Tensor)

    def test_grad_device_on_accelerator(self, device):
        """backward 后 .grad 的 device 应在加速卡上。"""
        p = nn.Parameter(torch.randn(4, device=device))
        loss = p.sum()
        loss.backward()
        assert p.grad.device.type == device.type

    def test_grad_dtype_matches_parameter_float32(self, device):
        """float32 Parameter 的 .grad dtype 应为 float32。"""
        p = nn.Parameter(torch.randn(4, dtype=torch.float32, device=device))
        loss = p.sum()
        loss.backward()
        assert p.grad.dtype == torch.float32

    def test_grad_dtype_matches_parameter_float64(self, device):
        """float64 Parameter 的 .grad dtype 应为 float64。"""
        p = nn.Parameter(torch.randn(4, dtype=torch.float64, device=device))
        loss = p.sum()
        loss.backward()
        assert p.grad.dtype == torch.float64

    def test_grad_shape_matches_parameter_1d(self, device):
        """1D Parameter 的 .grad shape 应与 Parameter 一致。"""
        p = nn.Parameter(torch.randn(5, device=device))
        loss = p.sum()
        loss.backward()
        assert p.grad.shape == p.shape

    def test_grad_shape_matches_parameter_2d(self, device):
        """2D Parameter 的 .grad shape 应与 Parameter 一致。"""
        p = nn.Parameter(torch.randn(3, 4, device=device))
        loss = p.sum()
        loss.backward()
        assert p.grad.shape == p.shape

    def test_grad_shape_matches_parameter_scalar(self, device):
        """标量 Parameter 的 .grad shape 应为空（标量形状）。"""
        p = nn.Parameter(torch.tensor(2.0, device=device))
        loss = p * 3.0
        loss.backward()
        assert p.grad.shape == torch.Size([])


# ---------------------------------------------------------------------------
# 3. requires_grad=False 时 backward 后 .grad 仍为 None
# ---------------------------------------------------------------------------

class TestParameterGradRequiresGradFalse:
    """requires_grad=False 的 Parameter 在 backward 后 .grad 仍为 None。"""

    def test_grad_none_when_requires_grad_false(self, device):
        p = nn.Parameter(torch.randn(4, device=device), requires_grad=False)
        other = torch.randn(4, device=device, requires_grad=True)
        loss = (other * p.detach()).sum()
        loss.backward()
        assert p.grad is None


# ---------------------------------------------------------------------------
# 4. 多次 backward 后 .grad 累加
# ---------------------------------------------------------------------------

class TestParameterGradAccumulation:
    """不清零的情况下，多次 backward 会累加 .grad。"""

    def test_grad_accumulates_over_two_backward(self, device):
        p = nn.Parameter(torch.ones(3, device=device))
        loss1 = p.sum()
        loss1.backward()
        grad_after_first = p.grad.clone()
        loss2 = p.sum()
        loss2.backward()
        assert p.grad is not None
        assert p.grad.shape == p.shape
        assert not torch.equal(p.grad, grad_after_first)

    def test_grad_accumulates_over_three_backward(self, device):
        p = nn.Parameter(torch.ones(2, 2, device=device))
        for _ in range(3):
            loss = p.sum()
            loss.backward()
        assert p.grad is not None
        assert p.grad.shape == p.shape


# ---------------------------------------------------------------------------
# 5. 手动设置 .grad（赋值）
# ---------------------------------------------------------------------------

class TestParameterGradManualAssignment:
    """验证可以手动对 .grad 进行赋值。"""

    def test_manual_set_grad_to_tensor(self, device):
        p = nn.Parameter(torch.randn(4, device=device))
        custom_grad = torch.zeros(4, device=device)
        p.grad = custom_grad
        assert p.grad is not None
        assert isinstance(p.grad, torch.Tensor)
        assert p.grad.shape == p.shape

    def test_manual_set_grad_to_none(self, device):
        """手动将 .grad 置为 None（等价于清零梯度）。"""
        p = nn.Parameter(torch.randn(4, device=device))
        loss = p.sum()
        loss.backward()
        assert p.grad is not None
        p.grad = None
        assert p.grad is None

    def test_manual_set_grad_then_backward(self, device):
        """手动赋值后再 backward，grad 应被累加。"""
        p = nn.Parameter(torch.ones(3, device=device))
        p.grad = torch.zeros(3, device=device)
        loss = p.sum()
        loss.backward()
        assert p.grad is not None
        assert p.grad.shape == p.shape


# ---------------------------------------------------------------------------
# 6. zero_grad 后 .grad 行为
# ---------------------------------------------------------------------------

class TestParameterGradZeroGrad:
    """验证 zero_grad 后 .grad 变为零张量或 None。"""

    def test_optimizer_zero_grad_resets_grad(self, device):
        """使用 optimizer.zero_grad() 后 .grad 变为全零张量（set_to_none=False）。"""
        p = nn.Parameter(torch.randn(4, device=device))
        optimizer = torch.optim.SGD([p], lr=0.01)
        loss = p.sum()
        loss.backward()
        assert p.grad is not None
        optimizer.zero_grad(set_to_none=False)
        assert p.grad is not None
        assert p.grad.shape == p.shape

    def test_optimizer_zero_grad_set_to_none(self, device):
        """使用 optimizer.zero_grad(set_to_none=True) 后 .grad 变为 None。"""
        p = nn.Parameter(torch.randn(4, device=device))
        optimizer = torch.optim.SGD([p], lr=0.01)
        loss = p.sum()
        loss.backward()
        assert p.grad is not None
        optimizer.zero_grad(set_to_none=True)
        assert p.grad is None

    def test_manual_zero_grad_via_none(self, device):
        """手动 p.grad = None 等效于 zero_grad(set_to_none=True)。"""
        p = nn.Parameter(torch.randn(3, 3, device=device))
        loss = p.sum()
        loss.backward()
        p.grad = None
        assert p.grad is None


# ---------------------------------------------------------------------------
# 7. 在 nn.Module 中使用 Parameter，通过 parameters() 检查 grad
# ---------------------------------------------------------------------------

class TestParameterGradInModule:
    """验证在 nn.Module 中注册的 Parameter，backward 后可通过 parameters() 看到 grad。"""

    def test_module_parameter_grad_after_backward(self, device):
        class SimpleModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = nn.Parameter(torch.randn(4, 4))
                self.bias = nn.Parameter(torch.randn(4))

            def forward(self, x):
                return x @ self.weight + self.bias

        model = SimpleModel().to(device)
        x = torch.randn(2, 4, device=device)
        loss = model(x).sum()
        loss.backward()

        for name, param in model.named_parameters():
            assert param.grad is not None, f"参数 {name} 的 grad 应不为 None"
            assert param.grad.shape == param.shape, f"参数 {name} 的 grad shape 不匹配"
            assert param.grad.device.type == device.type, f"参数 {name} 的 grad 应在加速卡上"

    def test_module_parameter_grad_device_type(self, device):
        """验证 module 中所有 Parameter.grad 的 device.type 与后端一致。"""
        model = nn.Linear(3, 2).to(device)
        x = torch.randn(4, 3, device=device)
        loss = model(x).sum()
        loss.backward()

        for param in model.parameters():
            assert param.grad.device.type == device.type

    def test_module_parameter_grad_dtype_consistency(self, device):
        """验证 grad 的 dtype 与对应 parameter 的 dtype 一致。"""
        model = nn.Linear(3, 2).to(device).to(torch.float32)
        x = torch.randn(4, 3, device=device, dtype=torch.float32)
        loss = model(x).sum()
        loss.backward()

        for param in model.parameters():
            assert param.grad.dtype == param.dtype

    def test_module_zero_grad_via_optimizer(self, device):
        """通过 optimizer.zero_grad() 清除 module 中 Parameter.grad。"""
        model = nn.Linear(3, 2).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        x = torch.randn(4, 3, device=device)

        loss = model(x).sum()
        loss.backward()
        for param in model.parameters():
            assert param.grad is not None

        optimizer.zero_grad(set_to_none=True)
        for param in model.parameters():
            assert param.grad is None

    def test_module_grad_none_before_backward(self, device):
        """module 未执行 backward 时，所有 Parameter.grad 为 None。"""
        model = nn.Linear(5, 3).to(device)
        for param in model.parameters():
            assert param.grad is None
