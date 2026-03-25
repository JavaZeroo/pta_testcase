"""
测试目的：
1. 验证 torch.autograd._unsafe_preserve_version_counter 在 NPU Tensor 上可作为上下文管理器正常使用。
2. 验证单个 Tensor 与 Tensor 元组两种入参形式在上下文内外的版本计数器恢复行为。
3. 验证不传参数、传入 None/非 Tensor、传入包含非法元素的 tuple 等异常场景。
4. 覆盖主要 dtype、单层/嵌套上下文、上下文内/外原地操作等常见使用路径。

API 名称：torch.autograd._unsafe_preserve_version_counter

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| 入参形式（单个 Tensor） | 已覆盖 | 传入 NPU Tensor，验证上下文可正常工作 |
| 入参形式（Tensor 元组） | 已覆盖 | 传入多个 NPU Tensor，验证 tuple 入参可正常工作 |
| 不传参数 | 已覆盖 | 直接调用时抛出 TypeError |
| None / 非 None | 已覆盖 | None、int、str、list 等非 Tensor 入参触发异常；NPU Tensor 作为非 None 正常入参 |
| tuple 内非法元素 | 已覆盖 | tuple 中混入非 Tensor 元素触发异常 |
| dtype | 已覆盖 | float16 / float32 / int32 |
| 上下文层级 | 已覆盖 | 单层与嵌套上下文均验证 |
| 原地操作场景 | 已覆盖 | 上下文内/外分别验证版本计数器行为 |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| 具体数值结果正确性 | 本测试聚焦版本计数器与上下文行为，不做数值比对 |
| 多 NPU 卡切换/跨卡通信 | 当前用例仅验证单卡 NPU 上的基础功能 |
| forward-mode AD 场景 | 该 API 文档已说明不适用于 forward-mode AD，因此不做扩展验证 |
| 复杂形状/stride 组合 | 该 API 关注版本计数器，与形状/stride 无直接关系 |
"""

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu_and_api():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.autograd._unsafe_preserve_version_counter 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.autograd._unsafe_preserve_version_counter 测试。")
    if not hasattr(torch.autograd, "_unsafe_preserve_version_counter"):
        pytest.skip("当前环境的 torch.autograd 不包含 _unsafe_preserve_version_counter，无法执行对应测试。")


@pytest.fixture()
def npu_tensor():
    _require_npu_and_api()
    return torch.ones((2, 2), device=torch.device("npu:0"))


def _make_npu_tensor(dtype):
    return torch.ones((2, 2), device=torch.device("npu:0"), dtype=dtype)


def test_unsafe_preserve_version_counter_callable_and_no_arg_raises():
    _require_npu_and_api()
    assert callable(torch.autograd._unsafe_preserve_version_counter)
    with pytest.raises(TypeError):
        torch.autograd._unsafe_preserve_version_counter()


@pytest.mark.parametrize("bad_arg", [None, 1, "abc", [1, 2]])
def test_unsafe_preserve_version_counter_non_tensor_arg_raises(bad_arg):
    _require_npu_and_api()
    with pytest.raises(AssertionError):
        with torch.autograd._unsafe_preserve_version_counter(bad_arg):
            pass


@pytest.mark.parametrize("dtype", [torch.float16, torch.float32, torch.int32])
@pytest.mark.parametrize("use_tuple", [False, True])
def test_unsafe_preserve_version_counter_preserve_inside_and_bump_outside(dtype, use_tuple):
    _require_npu_and_api()
    tensor = _make_npu_tensor(dtype)
    tensor_pair = (_make_npu_tensor(dtype), _make_npu_tensor(dtype))
    target = tensor_pair if use_tuple else tensor
    tensors = tensor_pair if use_tuple else (tensor,)
    before_versions = tuple(t._version for t in tensors)

    assert tensors[0].device.type == "npu"

    with torch.autograd._unsafe_preserve_version_counter(target):
        for item, before in zip(tensors, before_versions):
            item.add_(1)
            assert item._version > before

    after_versions = tuple(t._version for t in tensors)
    assert after_versions == before_versions

    for item, after in zip(tensors, after_versions):
        item.add_(1)
        assert item._version > after


def test_unsafe_preserve_version_counter_nested_contexts_on_npu(npu_tensor):
    before = npu_tensor._version
    with torch.autograd._unsafe_preserve_version_counter(npu_tensor):
        npu_tensor.zero_()
        assert npu_tensor._version > before
        with torch.autograd._unsafe_preserve_version_counter(npu_tensor):
            npu_tensor.fill_(2)
            assert npu_tensor._version > before
        assert npu_tensor._version > before

    assert npu_tensor._version == before
    npu_tensor.zero_()
    assert npu_tensor._version > before


def test_unsafe_preserve_version_counter_tuple_with_invalid_element_raises():
    _require_npu_and_api()
    bad_tuple = (_make_npu_tensor(torch.float32), 1)
    with pytest.raises(AttributeError):
        with torch.autograd._unsafe_preserve_version_counter(bad_tuple):
            pass
