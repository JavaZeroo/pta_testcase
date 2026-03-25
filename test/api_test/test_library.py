"""
测试目的：
1. 验证 torch.library.opcheck 在 NPU 上可正常处理内置算子与自定义算子，覆盖默认参数、显式参数与异常场景。
2. 验证 torch.library.custom_op + register_fake 的基础组合能够在 NPU 张量上完成注册与派发检查。
3. 通过 pytest.raises 覆盖非法 op、非法 test_utils 以及 NPU 后端暂不支持的 autograd_registration 检查路径，并检查 raise_exception=False 的返回分支。

API 名称：torch.library

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| op | 已覆盖 | 覆盖 `torch.ops.aten.sin.default`（`OpOverload`）、`torch.ops.aten.sin`（`OpOverloadPacket`）、`CustomOpDef`、以及非法函数对象 |
| args | 已覆盖 | 覆盖单 Tensor 参数、Tensor + 标量组合参数，且均在 NPU 上执行 |
| kwargs | 已覆盖 | 覆盖省略/`None` 以及非空字典两种传参方式 |
| test_utils | 已覆盖 | 覆盖字符串、列表以及非法字符串；默认全集因 NPU 后端限制不执行 |
| raise_exception | 已覆盖 | 覆盖默认 `True` 和显式 `False` |
| atol/rtol | 已覆盖 | 覆盖显式传入与省略两种情况 |
| 设备 | 已覆盖 | 所有有效测试均使用 `npu:0` 张量执行 |
| 结果分支 | 已覆盖 | 覆盖成功返回与异常抛出两类场景 |
| autograd_registration | 已覆盖 | 在 NPU 上显式触发 `NotImplementedError`，说明该检查当前仅支持 CPU/CUDA |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 多 NPU 设备/跨卡切换 | 当前测试目标为单卡基础功能验证，不依赖多卡环境 |
| CPU/CUDA 交叉设备对比 | 本文件要求所有测试在 NPU 上运行，不引入其他设备分支 |
| `test_autograd_registration` 的成功路径 | 当前 NPU 后端对该检查明确返回不支持，因此仅验证异常分支 |
| 更复杂的 mutates_args / alias / tags 组合 | 仅覆盖 opcheck 的核心可用性，避免与其他 custom_op 专项测试重复 |
| 数值正确性精度校验 | 本测试聚焦接口注册、派发与参数校验，不做具体数值比对 |
"""

import uuid
from typing import Optional

import pytest

import torch
import torch_npu  # noqa: F401
from torch.testing._internal.optests.generate_tests import OpCheckError


def _require_npu() -> None:
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.library 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.library 测试。")


def _unique_namespace() -> str:
    return f"pta_library_{uuid.uuid4().hex}"


@pytest.fixture()
def npu_tensor():
    _require_npu()
    return torch.randn(4, device="npu:0", requires_grad=True)


def _build_custom_op(namespace: str):
    @torch.library.custom_op(f"{namespace}::scale_add", mutates_args=())
    def scale_add(
        x: torch.Tensor,
        scale: float,
        bias: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        out = x * scale
        if bias is not None:
            out = out + bias
        return out

    @scale_add.register_fake
    def _(x, scale, bias=None):
        return torch.empty_like(x)

    def setup_context(ctx, inputs, output):
        _, scale, bias = inputs
        ctx.scale = scale
        ctx.has_bias = bias is not None

    def backward(ctx, grad):
        grad_x = grad * ctx.scale
        grad_bias = grad if ctx.has_bias else None
        return grad_x, None, grad_bias

    scale_add.register_autograd(backward, setup_context=setup_context)
    return scale_add


def test_opcheck_builtin_aten_sin_default_and_tolerances_on_npu(npu_tensor):
    """NPU 正常场景：验证内置 OpOverload 在默认参数、test_utils 列表和 atol/rtol 显式传参时均可通过 opcheck。"""
    npu_no_grad = npu_tensor.detach()

    result = torch.library.opcheck(
        torch.ops.aten.sin.default,
        (npu_no_grad,),
        test_utils=["test_schema", "test_faketensor", "test_aot_dispatch_dynamic"],
    )
    assert result == {
        "test_schema": "SUCCESS",
        "test_faketensor": "SUCCESS",
        "test_aot_dispatch_dynamic": "SUCCESS",
    }

    subset = torch.library.opcheck(
        torch.ops.aten.sin.default,
        (npu_no_grad,),
        test_utils=["test_schema", "test_faketensor"],
        atol=1e-5,
        rtol=1e-4,
    )
    assert subset == {
        "test_schema": "SUCCESS",
        "test_faketensor": "SUCCESS",
    }


def test_opcheck_custom_op_with_kwargs_and_raise_exception_false_on_npu(npu_tensor):
    """NPU 正常场景：验证 CustomOpDef 在 kwargs 非空、覆盖 fake 注册检查且 raise_exception=False 时可返回结果字典。"""
    namespace = _unique_namespace()
    scale_add = _build_custom_op(namespace)
    npu_no_grad = npu_tensor.detach()
    bias = torch.randn_like(npu_no_grad)

    result = torch.library.opcheck(
        scale_add,
        (npu_no_grad, 0.5),
        kwargs={"bias": bias},
        test_utils=["test_schema", "test_faketensor"],
        raise_exception=False,
    )

    assert result == {
        "test_schema": "SUCCESS",
        "test_faketensor": "SUCCESS",
    }


def test_opcheck_builtin_aten_sin_packet_requires_unique_overload_on_npu(npu_tensor):
    """NPU 异常场景：验证 OpOverloadPacket 传入非唯一重载时会抛出明确错误。"""
    with pytest.raises(
        RuntimeError,
        match=r"opcheck can only test operators without overloads",
    ):
        torch.library.opcheck(torch.ops.aten.sin, (npu_tensor.detach(),))


def test_opcheck_autograd_registration_not_supported_on_npu(npu_tensor):
    """NPU 异常场景：验证 autograd_registration 检查在当前 NPU 后端会明确报出不支持。"""
    with pytest.raises(
        OpCheckError,
        match="test_autograd_registration failed with autograd_registration_check: NYI devices other than CPU/CUDA",
    ) as exc_info:
        torch.library.opcheck(
            torch.ops.aten.sin.default,
            (npu_tensor,),
            test_utils="test_autograd_registration",
        )
    assert isinstance(exc_info.value.__cause__, NotImplementedError)


def test_opcheck_invalid_inputs_raise_on_npu(npu_tensor):
    """NPU 异常场景：验证非法 op 与非法 test_utils 会被 opcheck 拒绝。"""
    with pytest.raises(ValueError, match="OpOverload"):
        torch.library.opcheck(torch.sin, (npu_tensor,))

    with pytest.raises(ValueError, match="test_utils to be subset of"):
        torch.library.opcheck(torch.ops.aten.sin.default, (npu_tensor,), test_utils="blah")
