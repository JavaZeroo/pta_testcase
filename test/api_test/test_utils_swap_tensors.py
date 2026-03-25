"""
测试目的：
1. 验证 torch.utils.swap_tensors 在 NPU 上可以正常执行，且交换后 Tensor 的对象身份保持不变，内部存储指针与元数据完成互换。
2. 覆盖正常交换、None / 非 Tensor 异常、weakref 异常、requires_grad 的反向传播异常、Tensor 子类 __slots__ 异常等分支。

API 名称：torch.utils.swap_tensors

覆盖的参数维度表：
| 维度 | 覆盖情况 | 说明 |
| --- | --- | --- |
| t1 是否为 Tensor | 已覆盖 | 覆盖 Tensor / None / 非 Tensor |
| t2 是否为 Tensor | 已覆盖 | 覆盖 Tensor / None / 非 Tensor |
| device | 已覆盖 | 所有用例均在 NPU 上运行 |
| dtype | 已覆盖 | 覆盖 float32、float16、int64，以及同 / 异 dtype 交换 |
| shape | 已覆盖 | 覆盖同 shape、异 shape 交换 |
| requires_grad | 已覆盖 | 覆盖普通 Tensor 与 requires_grad=True Tensor |
| Python slots / __slots__ | 已覆盖 | 覆盖相同 slots 正常交换、不同 slots 抛错 |
| weakref 状态 | 已覆盖 | 覆盖存在 weakref 时抛错 |
| 返回值 | 已覆盖 | 验证 swap_tensors 为原地操作并返回 None |

未覆盖项及原因：
| 未覆盖项 | 原因 |
| --- | --- |
| CPU/CUDA 与 NPU 跨设备交换 | 当前测试要求全部在 NPU 上运行，避免混合设备依赖 |
| 多 NPU 卡 / 跨卡交换 | 当前仅验证单卡 NPU 基本语义，不强依赖多卡拓扑 |
| 交换后的具体数值正确性 | 该 API 的重点是交换语义与异常分支，不做具体数值校验 |
"""

import weakref

import pytest

import torch
import torch_npu  # noqa: F401


def _require_npu():
    if not hasattr(torch, "npu"):
        pytest.skip("当前环境未暴露 torch.npu，无法在 NPU 上执行 torch.utils.swap_tensors 测试。")
    if not torch.npu.is_available():
        pytest.skip("当前环境 NPU 不可用，无法在 NPU 上执行 torch.utils.swap_tensors 测试。")


def _make_npu_tensor(shape, dtype=torch.float32, requires_grad=False):
    _require_npu()
    return torch.empty(shape, device=torch.device("npu"), dtype=dtype, requires_grad=requires_grad)


def _snapshot_tensor(tensor):
    return {
        "shape": tuple(tensor.shape),
        "stride": tuple(tensor.stride()),
        "dtype": tensor.dtype,
        "device_type": tensor.device.type,
        "requires_grad": tensor.requires_grad,
        "data_ptr": tensor.data_ptr(),
    }


class _SlotTensorAB(torch.Tensor):
    __slots__ = ("alpha", "beta")

    @staticmethod
    def __new__(cls, base_tensor, alpha=None, beta=None):
        return torch.Tensor._make_subclass(cls, base_tensor, base_tensor.requires_grad)

    def __init__(self, base_tensor, alpha=None, beta=None):
        self.alpha = alpha
        self.beta = beta


class _SlotTensorBA(torch.Tensor):
    __slots__ = ("beta", "alpha")

    @staticmethod
    def __new__(cls, base_tensor, alpha=None, beta=None):
        return torch.Tensor._make_subclass(cls, base_tensor, base_tensor.requires_grad)

    def __init__(self, base_tensor, alpha=None, beta=None):
        self.beta = beta
        self.alpha = alpha


class _SlotTensorAC(torch.Tensor):
    __slots__ = ("alpha", "gamma")

    @staticmethod
    def __new__(cls, base_tensor, alpha=None, gamma=None):
        return torch.Tensor._make_subclass(cls, base_tensor, base_tensor.requires_grad)

    def __init__(self, base_tensor, alpha=None, gamma=None):
        self.alpha = alpha
        self.gamma = gamma


@pytest.fixture()
def npu_pair_same_shape_same_dtype():
    _require_npu()
    return _make_npu_tensor((2, 2), torch.float32), _make_npu_tensor((2, 2), torch.float32)


@pytest.mark.parametrize(
    "t1_factory, t2_factory",
    [
        (
            lambda: _make_npu_tensor((2, 2), torch.float32),
            lambda: _make_npu_tensor((2, 2), torch.float32),
        ),
        (
            lambda: _make_npu_tensor((2,), torch.float32),
            lambda: _make_npu_tensor((2, 3), torch.float32),
        ),
        (
            lambda: _make_npu_tensor((4,), torch.float32),
            lambda: _make_npu_tensor((4,), torch.float16),
        ),
        (
            lambda: _make_npu_tensor((3, 1), torch.float16),
            lambda: _make_npu_tensor((1, 3), torch.int64),
        ),
    ],
)
def test_swap_tensors_npu_normal_cases(t1_factory, t2_factory):
    """验证正常 Tensor-Tensor 场景下，shape / dtype / stride / data_ptr 会互换且对象身份保持不变。"""
    _require_npu()

    t1 = t1_factory()
    t2 = t2_factory()
    holder = [t1]

    before_t1 = _snapshot_tensor(t1)
    before_t2 = _snapshot_tensor(t2)

    ret = torch.utils.swap_tensors(t1, t2)

    assert ret is None
    assert holder[0] is t1
    assert _snapshot_tensor(t1) == before_t2
    assert _snapshot_tensor(t2) == before_t1
    assert t1.device.type == "npu"
    assert t2.device.type == "npu"


def test_swap_tensors_same_shape_same_dtype_fixture_case(npu_pair_same_shape_same_dtype):
    """补充验证同 shape、同 dtype 的 NPU Tensor 交换后，原地语义与指针互换关系保持正确。"""
    _require_npu()

    t1, t2 = npu_pair_same_shape_same_dtype
    before_t1 = _snapshot_tensor(t1)
    before_t2 = _snapshot_tensor(t2)

    torch.utils.swap_tensors(t1, t2)

    assert _snapshot_tensor(t1) == before_t2
    assert _snapshot_tensor(t2) == before_t1


def test_swap_tensors_swaps_dict_and_self_returning_methods():
    """验证 swap_tensors 会交换 __dict__，且交换后返回 self 的原地方法仍返回正确对象。"""
    _require_npu()

    t1 = _make_npu_tensor((2, 2), torch.float32)
    t2 = _make_npu_tensor((2, 2), torch.float32)
    t1.left_tag = "from_t1"
    t1.shared = {"owner": "t1"}
    t2.right_tag = "from_t2"
    t2.shared = {"owner": "t2"}

    before_t1_dict = dict(t1.__dict__)
    before_t2_dict = dict(t2.__dict__)

    torch.utils.swap_tensors(t1, t2)

    assert t1.__dict__ == before_t2_dict
    assert t2.__dict__ == before_t1_dict
    assert t1.fill_(0.5) is t1
    assert t2.fill_(0.5) is t2


@pytest.mark.parametrize(
    "bad_t1, bad_t2",
    [
        (1, lambda: _make_npu_tensor((2,), torch.float32)),
        (None, lambda: _make_npu_tensor((2,), torch.float32)),
        (lambda: _make_npu_tensor((2,), torch.float32), None),
        ("abc", "def"),
    ],
)
def test_swap_tensors_non_tensor_args_raise_attribute_error(bad_t1, bad_t2):
    """验证 None / 非 Tensor 入参会抛出异常，并使用 pytest.raises 覆盖异常路径。"""
    _require_npu()

    t1 = bad_t1() if callable(bad_t1) else bad_t1
    t2 = bad_t2() if callable(bad_t2) else bad_t2

    with pytest.raises(AttributeError):
        torch.utils.swap_tensors(t1, t2)


def test_swap_tensors_weakref_raises_runtime_error():
    """验证当 Tensor 持有 weakref 时，swap_tensors 会抛出 RuntimeError。"""
    _require_npu()

    t1 = _make_npu_tensor((2,), torch.float32)
    t2 = _make_npu_tensor((2,), torch.float32)
    ref = weakref.ref(t1)
    assert ref() is t1

    with pytest.raises(RuntimeError, match="has weakref"):
        torch.utils.swap_tensors(t1, t2)


def test_swap_tensors_poisoned_accumulate_grad_raises_runtime_error():
    """验证 requires_grad 场景下，交换后对旧计算图 backward 会触发 poison 异常。"""
    _require_npu()

    t1 = _make_npu_tensor((2,), torch.float32, requires_grad=True)
    t2 = _make_npu_tensor((2,), torch.float32)
    out = t1 * 2

    torch.utils.swap_tensors(t1, t2)

    with pytest.raises(RuntimeError, match="poisoned by swap_tensors"):
        out.sum().backward()


def test_swap_tensors_same_slots_subclass_swap_and_different_slots_error():
    """验证 Tensor 子类相同 slots 可正常交换，不同 slots 会抛出 RuntimeError。"""
    _require_npu()

    a = _SlotTensorAB(_make_npu_tensor((2,), torch.float32), alpha="left", beta="keep")
    b = _SlotTensorAB(_make_npu_tensor((2,), torch.float32), alpha="right", beta="stay")
    before_a = _snapshot_tensor(a)
    before_b = _snapshot_tensor(b)

    torch.utils.swap_tensors(a, b)

    assert _snapshot_tensor(a) == before_b
    assert _snapshot_tensor(b) == before_a
    assert a.alpha == "right"
    assert a.beta == "stay"
    assert b.alpha == "left"
    assert b.beta == "keep"

    c = _SlotTensorAC(_make_npu_tensor((2,), torch.float32), alpha="x", gamma="y")
    with pytest.raises(RuntimeError, match="different slots"):
        torch.utils.swap_tensors(a, c)
