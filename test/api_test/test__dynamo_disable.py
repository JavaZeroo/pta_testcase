# 测试目的：验证 torch._dynamo.disable 在加速卡（NPU/GPU）环境中的基本功能行为
# API 名称：torch._dynamo.disable(fn=None, recursive=True)
#
# 覆盖参数维度：
# | 覆盖维度           | 说明                                                  | 覆盖情况                                    |
# |--------------------|-------------------------------------------------------|---------------------------------------------|
# | 空/非空（None）    | fn=None（装饰器工厂）与 fn 非 None（直接装饰函数）    | 两路径均覆盖                                |
# | 枚举选项           | recursive=True / recursive=False                      | 两值均覆盖                                  |
# | 参数类型           | fn 为普通函数 / lambda / nn.Module 子类               | 均覆盖                                      |
# | 传参与不传参       | recursive 使用默认值 / 显式传入 True / 显式传入 False | 均覆盖                                      |
# | 等价类/边界值      | 单参/多参函数、返回标量/元组、多步加速卡运算          | 覆盖主路径                                  |
# | 正常传参场景       | 被装饰函数在加速卡上正常调用，返回合理 Tensor         | 全部主路径覆盖                              |
# | 异常传参场景       | 无稳定异常证据，不生成异常测试                        | N/A                                         |
#
# 未覆盖项：
#   - torch.compile 集成行为：需要完整 Dynamo 运行时支持，不适合基础功能测试。
#   - innermost_fn 对多层 wrapper 的剥离逻辑：属于内部实现细节，不做白盒测试。
#   - DisableContext 作为 with 语句上下文管理器：内部实现，公开 API 用法已全覆盖。

import pytest
import torch
import torch.nn as nn


if not hasattr(torch, "_dynamo") or not hasattr(torch._dynamo, "disable"):
    pytest.skip(
        "torch._dynamo.disable not available in this PyTorch version",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# 辅助：在加速卡上创建 tensor
# ---------------------------------------------------------------------------

def _device_tensor(device, rows=4, cols=4):
    return torch.randn(rows, cols, device=device)


# ===========================================================================
# 分支 1：recursive=True（默认） + fn 非 None → 直接作为装饰器
# ===========================================================================

class TestDisableDirectDecorator:
    """@torch._dynamo.disable 直接装饰函数（recursive=True，fn 不为 None）。"""

    def test_disable_direct_decorator_plain_function(self, device):
        """直接装饰普通函数，函数可在加速卡上正常调用并返回 Tensor"""
        @torch._dynamo.disable
        def add_one(x):
            return x + 1

        x = _device_tensor(device)
        result = add_one(x)
        assert result is not None
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type

    def test_disable_direct_decorator_returns_callable(self):
        """直接装饰后，被装饰对象依然可调用"""
        @torch._dynamo.disable
        def identity(x):
            return x

        assert callable(identity)

    def test_disable_direct_decorator_output_shape_preserved(self, device):
        """直接装饰的函数，输出 Tensor 形状与输入一致"""
        @torch._dynamo.disable
        def double(x):
            return x * 2

        x = _device_tensor(device)
        result = double(x)
        assert result.shape == x.shape

    def test_disable_direct_decorator_with_multiple_args(self, device):
        """直接装饰接受多参数的函数"""
        @torch._dynamo.disable
        def add_tensors(a, b):
            return a + b

        a = _device_tensor(device)
        b = _device_tensor(device)
        result = add_tensors(a, b)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type

    def test_disable_direct_decorator_applied_via_call(self, device):
        """通过函数调用而非装饰器语法手动应用 disable(fn)"""
        def raw_fn(x):
            return x + x

        disabled_fn = torch._dynamo.disable(raw_fn)
        assert callable(disabled_fn)
        x = _device_tensor(device)
        result = disabled_fn(x)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type


# ===========================================================================
# 分支 2：recursive=True + fn 为 None → 作为装饰器工厂 / 上下文
# ===========================================================================

class TestDisableFactoryDefaultRecursive:
    """torch._dynamo.disable() 不传 fn，返回 DisableContext，再用于装饰。"""

    def test_disable_factory_no_args(self, device):
        """不传任何参数调用 disable()，返回可用装饰器的工厂"""
        @torch._dynamo.disable()
        def multiply(x, scale):
            return x * scale

        x = _device_tensor(device)
        result = multiply(x, 2.0)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type

    def test_disable_factory_explicit_recursive_true(self, device):
        """显式传 recursive=True，行为与无参工厂等价"""
        @torch._dynamo.disable(recursive=True)
        def subtract(x, y):
            return x - y

        a = _device_tensor(device)
        b = _device_tensor(device)
        result = subtract(a, b)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type

    def test_disable_factory_returns_callable(self):
        """fn=None 时返回的对象本身可调用（可作为装饰器）"""
        ctx = torch._dynamo.disable()
        assert callable(ctx)

    def test_disable_factory_fn_none_explicit_then_apply(self, device):
        """显式传 fn=None, recursive=True，之后手动应用到函数上"""
        disable_ctx = torch._dynamo.disable(fn=None, recursive=True)

        def relu_fn(x):
            return torch.relu(x)

        decorated = disable_ctx(relu_fn)
        assert callable(decorated)
        x = _device_tensor(device)
        result = decorated(x)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type

    def test_disable_factory_nn_module_forward(self, device):
        """工厂模式装饰 nn.Module 子类，forward 可在加速卡上正常运行"""
        @torch._dynamo.disable()
        class SimpleModel(nn.Module):
            def __init__(self, dev):
                super().__init__()
                self.linear = nn.Linear(4, 4).to(dev)

            def forward(self, x):
                return self.linear(x)

        model = SimpleModel(device)
        x = _device_tensor(device)
        result = model(x)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type
        assert result.shape == (4, 4)


# ===========================================================================
# 分支 3：recursive=False → return skip(fn)
# ===========================================================================

class TestDisableRecursiveFalse:
    """recursive=False 走 skip 分支。"""

    def test_disable_recursive_false_direct(self, device):
        """recursive=False 直接装饰函数，函数在加速卡上正常执行"""
        @torch._dynamo.disable(recursive=False)
        def matmul_fn(a, b):
            return torch.mm(a, b)

        a = torch.randn(4, 4, device=device)
        b = torch.randn(4, 4, device=device)
        result = matmul_fn(a, b)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type
        assert result.shape == (4, 4)

    def test_disable_recursive_false_returns_callable(self):
        """recursive=False 装饰后，被装饰对象仍可调用"""
        @torch._dynamo.disable(recursive=False)
        def identity(x):
            return x

        assert callable(identity)

    def test_disable_recursive_false_fn_none(self):
        """recursive=False + fn=None，返回值可调用（可作为装饰器工厂）"""
        result = torch._dynamo.disable(fn=None, recursive=False)
        assert callable(result)

    def test_disable_recursive_false_with_ops(self, device):
        """recursive=False 装饰的函数可执行多步加速卡运算，形状和设备保持正确"""
        @torch._dynamo.disable(recursive=False)
        def compute(x):
            y = torch.relu(x)
            z = y * 2 + 1
            return z

        x = _device_tensor(device)
        result = compute(x)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type
        assert result.shape == x.shape

    def test_disable_recursive_false_applied_via_call(self, device):
        """通过函数调用而非装饰器语法应用 recursive=False"""
        def raw_fn(x):
            return x - 1

        disabled_fn = torch._dynamo.disable(raw_fn, recursive=False)
        assert callable(disabled_fn)
        x = _device_tensor(device)
        result = disabled_fn(x)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type


# ===========================================================================
# 综合场景：更多返回类型与使用模式
# ===========================================================================

class TestDisableIntegration:
    """综合验证被装饰函数在加速卡上的返回类型和设备行为"""

    def test_decorated_function_returns_scalar_tensor(self, device):
        """被装饰函数返回标量 Tensor（0 维），类型和设备正确"""
        @torch._dynamo.disable
        def sum_tensor(x):
            return x.sum()

        x = _device_tensor(device)
        result = sum_tensor(x)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type
        assert result.ndim == 0

    def test_decorated_function_returns_tuple(self, device):
        """被装饰函数返回多值元组，每个元素均为加速卡 Tensor"""
        @torch._dynamo.disable
        def split_fn(x):
            return x[:2], x[2:]

        x = torch.randn(4, 4, device=device)
        a, b = split_fn(x)
        assert isinstance(a, torch.Tensor)
        assert isinstance(b, torch.Tensor)
        assert a.device.type == device.type
        assert b.device.type == device.type

    def test_disable_nn_module_class_direct(self, device):
        """直接对 nn.Module 子类使用 @torch._dynamo.disable（分支 1 路径）"""
        @torch._dynamo.disable
        class TinyNet(nn.Module):
            def __init__(self, dev):
                super().__init__()
                self.fc = nn.Linear(4, 2).to(dev)

            def forward(self, x):
                return self.fc(x)

        model = TinyNet(device)
        x = _device_tensor(device)
        result = model(x)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type
        assert result.shape == (4, 2)

    def test_disable_recursive_true_and_false_both_callable_and_runnable(self, device):
        """同时验证 recursive=True/False 装饰相同逻辑，结果均可调用并产生加速卡 Tensor"""
        def make_fn():
            return lambda x: x * 3

        fn_true = torch._dynamo.disable(make_fn(), recursive=True)
        fn_false = torch._dynamo.disable(make_fn(), recursive=False)

        x = _device_tensor(device)
        r1 = fn_true(x)
        r2 = fn_false(x)

        assert isinstance(r1, torch.Tensor)
        assert isinstance(r2, torch.Tensor)
        assert r1.device.type == device.type
        assert r2.device.type == device.type
        assert r1.shape == x.shape
        assert r2.shape == x.shape

    def test_disable_lambda_function(self, device):
        """对 lambda 函数使用 disable，加速卡上可正常调用"""
        fn = torch._dynamo.disable(lambda x: x * 2 + 1)
        assert callable(fn)
        x = _device_tensor(device)
        result = fn(x)
        assert isinstance(result, torch.Tensor)
        assert result.device.type == device.type
