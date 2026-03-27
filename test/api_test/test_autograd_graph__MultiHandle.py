# 测试目的：验证 torch.autograd.graph._MultiHandle 在加速卡（NPU/GPU）上的接口行为
# API 名称：torch.autograd.graph._MultiHandle
#
# 覆盖维度表：
#
# | 覆盖维度         | 说明                                                         | 覆盖情况                                       |
# |------------------|--------------------------------------------------------------|------------------------------------------------|
# | 空/非空          | handles 参数为空元组与非空元组                               | 已覆盖：空元组、单个 handle、多个 handle        |
# | 枚举选项         | N/A（无枚举型入参）                                          | N/A                                            |
# | 参数类型         | handles 为 tuple[RemovableHandle, ...]                        | 已覆盖：空元组、单元素元组、多元素元组          |
# | 传参与不传参     | __init__ 必填参数 handles                                     | 已覆盖：传入不同长度的 tuple                    |
# | 等价类/边界值    | 空 tuple、单个 handle、多个 handle                            | 已覆盖                                          |
# | 正常传参场景     | 合法输入下 API 可正常调用                                     | 已覆盖：构造、remove()、上下文管理器、pickle    |
# | 异常传参场景     | N/A（无明确文档说明会稳定抛异常的非法输入场景）              | 未覆盖，原因：无证据表明 PyTorch 对非法输入会稳定抛出异常 |
#
# 未覆盖项及原因：
# - 异常场景：_MultiHandle 是内部 API，无公开文档说明合法异常路径；
#   为避免写出脆弱的负例测试，所有异常场景均省略。

import pickle

import pytest
import torch


def _identity_hook(grad):
    """模块级具名函数，用于替代 lambda 以支持 pickle 序列化。"""
    return grad


def _make_handle(device):
    """在加速卡 tensor 上注册 hook 并返回 RemovableHandle。"""
    x = torch.randn(3, requires_grad=True, device=device)
    handle = x.register_hook(_identity_hook)
    return handle, x


class TestMultiHandleImport:
    """验证类可导入、可访问。"""

    def test_class_exists(self):
        assert hasattr(torch.autograd.graph, "_MultiHandle"), (
            "_MultiHandle not found in torch.autograd.graph"
        )

    def test_class_is_type(self):
        cls = torch.autograd.graph._MultiHandle
        assert isinstance(cls, type)


class TestMultiHandleConstruction:
    """验证 _MultiHandle 的构造行为。"""

    def test_construct_with_empty_tuple(self):
        cls = torch.autograd.graph._MultiHandle
        mh = cls(())
        assert mh is not None
        assert isinstance(mh, cls)

    def test_construct_with_single_handle(self, device):
        cls = torch.autograd.graph._MultiHandle
        handle, _ = _make_handle(device)
        mh = cls((handle,))
        assert isinstance(mh, cls)

    def test_construct_with_multiple_handles(self, device):
        cls = torch.autograd.graph._MultiHandle
        h1, _ = _make_handle(device)
        h2, _ = _make_handle(device)
        h3, _ = _make_handle(device)
        mh = cls((h1, h2, h3))
        assert isinstance(mh, cls)

    def test_inherits_from_removable_handle(self):
        cls = torch.autograd.graph._MultiHandle
        mh = cls(())
        assert isinstance(mh, torch.utils.hooks.RemovableHandle)


class TestMultiHandleRemove:
    """验证 remove() 方法行为。"""

    def test_remove_empty_handles(self):
        cls = torch.autograd.graph._MultiHandle
        mh = cls(())
        mh.remove()

    def test_remove_single_handle(self, device):
        cls = torch.autograd.graph._MultiHandle
        handle, _ = _make_handle(device)
        mh = cls((handle,))
        mh.remove()

    def test_remove_multiple_handles(self, device):
        cls = torch.autograd.graph._MultiHandle
        h1, _ = _make_handle(device)
        h2, _ = _make_handle(device)
        mh = cls((h1, h2))
        mh.remove()

    def test_hook_inactive_after_remove(self, device):
        """remove() 后，底层 hook 不再触发（钩子计数不变）。"""
        cls = torch.autograd.graph._MultiHandle
        counter = {"count": 0}

        def counting_hook(grad):
            counter["count"] += 1
            return grad

        x = torch.randn(3, requires_grad=True, device=device)
        raw_handle = x.register_hook(counting_hook)
        mh = cls((raw_handle,))

        (x * 2).sum().backward()
        count_before = counter["count"]

        mh.remove()

        x.grad = None
        (x * 3).sum().backward()
        assert counter["count"] == count_before


class TestMultiHandleContextManager:
    """验证上下文管理器（__enter__ / __exit__）行为。"""

    def test_context_manager_empty(self):
        cls = torch.autograd.graph._MultiHandle
        with cls(()):
            pass

    def test_context_manager_single_handle(self, device):
        cls = torch.autograd.graph._MultiHandle
        handle, _ = _make_handle(device)
        with cls((handle,)) as mh:
            assert mh is not None

    def test_context_manager_multiple_handles(self, device):
        cls = torch.autograd.graph._MultiHandle
        h1, _ = _make_handle(device)
        h2, _ = _make_handle(device)
        with cls((h1, h2)):
            pass

    def test_hook_inactive_after_context_exit(self, device):
        """with 块退出后，hooks 不再活跃。"""
        cls = torch.autograd.graph._MultiHandle
        counter = {"count": 0}

        def counting_hook(grad):
            counter["count"] += 1
            return grad

        x = torch.randn(3, requires_grad=True, device=device)
        raw_handle = x.register_hook(counting_hook)

        with cls((raw_handle,)):
            pass

        count_after_exit = counter["count"]
        x.grad = None
        (x * 5).sum().backward()
        assert counter["count"] == count_after_exit


class TestMultiHandlePickle:
    """验证 __getstate__ / __setstate__ 支持 pickle 序列化。"""

    def test_getstate_empty(self):
        cls = torch.autograd.graph._MultiHandle
        mh = cls(())
        state = mh.__getstate__()
        assert isinstance(state, tuple)

    def test_getstate_with_handles(self, device):
        cls = torch.autograd.graph._MultiHandle
        h1, _ = _make_handle(device)
        h2, _ = _make_handle(device)
        mh = cls((h1, h2))
        state = mh.__getstate__()
        assert isinstance(state, tuple)
        assert len(state) == 2

    def test_setstate_restores(self, device):
        cls = torch.autograd.graph._MultiHandle
        h1, _ = _make_handle(device)
        mh_original = cls((h1,))
        state = mh_original.__getstate__()

        mh_restored = cls.__new__(cls)
        mh_restored.__setstate__(state)
        assert isinstance(mh_restored, cls)

    def test_pickle_round_trip_empty(self):
        cls = torch.autograd.graph._MultiHandle
        mh = cls(())
        data = pickle.dumps(mh)
        mh2 = pickle.loads(data)
        assert isinstance(mh2, cls)

    def test_pickle_round_trip_with_handles(self, device):
        cls = torch.autograd.graph._MultiHandle
        h1, _ = _make_handle(device)
        h2, _ = _make_handle(device)
        mh = cls((h1, h2))
        data = pickle.dumps(mh)
        mh2 = pickle.loads(data)
        assert isinstance(mh2, cls)
