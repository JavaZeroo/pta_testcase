"""
测试目的：
1. 验证 torch.compiler.is_compiling 在 NPU 环境下可正常调用，且无参数接口、返回类型、可调用性符合预期。
2. 验证在 torch.compile 编译区域内的行为（如当前环境支持），并覆盖传参异常场景。
3. 说明该 API 为无参接口，因此部分“None/非None、枚举、类型、边界值”维度不适用。

API 名称：torch.compiler.is_compiling

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 是否传参 | 已覆盖 | 验证无参正常调用，以及传入位置参数/关键字参数时抛出 TypeError |
| None/非None | 不适用 | 该 API 无任何入参，无法构造有效的 None/非None 入参组合 |
| 主要枚举值 | 不适用 | 该 API 无枚举型参数 |
| 主要类型 | 不适用 | 该 API 无类型型参数 |
| 正常场景 | 已覆盖 | 验证编译外返回 bool，且在可用时验证编译内路径 |
| 异常场景 | 已覆盖 | 验证错误传参时抛出 TypeError |
| 边界值 | 不适用 | 该 API 无数值/范围型入参，无法定义边界值 |
| NPU 运行 | 已覆盖 | 使用 torch_npu 并通过 NPU tensor 及 torch.compile 路径执行测试 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| None/非None、主要枚举值、主要类型、边界值 | API 无入参，相关维度不适用 |
| 具体编译图优化、缓存、性能 | 本用例聚焦 API 行为，不校验编译器内部实现细节 |
| 多 NPU 卡切换 | 当前用例仅验证单卡 NPU 上的基本功能，不依赖多卡环境 |
| 不同 torch.compile backend 的全量组合 | 仅使用最基础的 eager 路径验证编译区域行为，避免过度依赖后端实现差异 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.compiler.is_compiling 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.compiler.is_compiling 测试。")


@pytest.fixture()
def npu_tensor():
    _require_npu()
    return torch.tensor([1.0], device=torch.device("npu:0"))


def test_torch_compiler_is_compiling_callable_and_return_false_outside_compile(npu_tensor):
    """验证可调用性、无参数接口、返回类型及编译外结果。"""
    assert callable(torch.compiler.is_compiling)
    assert npu_tensor.device.type == "npu"

    out_1 = torch.compiler.is_compiling()
    out_2 = torch.compiler.is_compiling()

    assert isinstance(out_1, bool)
    assert isinstance(out_2, bool)
    assert out_1 is False
    assert out_2 is False
    assert npu_tensor.device.type == "npu"


def test_torch_compiler_is_compiling_with_arguments_raises_typeerror(npu_tensor):
    """验证传入参数时抛出 TypeError。"""
    assert npu_tensor.device.type == "npu"

    with pytest.raises(TypeError):
        torch.compiler.is_compiling(1)

    with pytest.raises(TypeError):
        torch.compiler.is_compiling(flag=True)

    with pytest.raises(TypeError):
        torch.compiler.is_compiling(None)


def test_torch_compiler_is_compiling_inside_compile_region_if_supported(npu_tensor):
    """验证在 torch.compile 编译区域内的调用行为。"""
    assert npu_tensor.device.type == "npu"

    if not hasattr(torch, "compile"):
        pytest.skip("当前环境未提供 torch.compile，无法验证编译区域行为。")

    def _fn(x):
        return torch.compiler.is_compiling(), x + 1

    try:
        compiled_fn = torch.compile(_fn, backend="eager")
        flag, out = compiled_fn(npu_tensor)
    except (RuntimeError, NotImplementedError) as exc:
        pytest.skip(f"当前 NPU 后端不支持 torch.compile eager 路径，无法验证编译区域行为：{exc}")

    assert isinstance(flag, bool)
    assert flag is True
    assert isinstance(out, torch.Tensor)
    assert out.device.type == "npu"
