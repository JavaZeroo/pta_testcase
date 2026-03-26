"""Shared fixtures for dual-backend (NPU / CUDA) API tests.

This conftest auto-detects the available accelerator and provides a ``device``
fixture so that every test file can run unchanged on both NPU and GPU machines.

Usage in tests
--------------
- Use the ``device`` fixture (or ``device_name`` for the string form) instead
  of hardcoding ``"npu"`` or ``"cuda"``.
- Do NOT import ``torch_npu`` at module level in test files; this conftest
  handles it.
- Assert device type with ``device.type`` (returns ``"npu"`` or ``"cuda"``).
"""

from __future__ import annotations

import pytest
import torch

# ---------------------------------------------------------------------------
# Conditional backend import
# ---------------------------------------------------------------------------

_BACKEND: str | None = None  # "npu" | "cuda" | None

try:
    import torch_npu  # noqa: F401

    if torch.npu.is_available():
        _BACKEND = "npu"
except ImportError:
    pass

if _BACKEND is None and torch.cuda.is_available():
    _BACKEND = "cuda"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def device_name() -> str:
    """Return the accelerator device name (``"npu:0"`` or ``"cuda:0"``)."""
    if _BACKEND is None:
        pytest.skip("No accelerator available (need NPU or CUDA)")
    return f"{_BACKEND}:0"


@pytest.fixture(scope="session")
def device(device_name: str) -> torch.device:
    """Return a ``torch.device`` pointing to the first accelerator."""
    return torch.device(device_name)


@pytest.fixture(scope="session")
def backend() -> str:
    """Return the backend type string: ``"npu"`` or ``"cuda"``."""
    if _BACKEND is None:
        pytest.skip("No accelerator available (need NPU or CUDA)")
    return _BACKEND


@pytest.fixture(autouse=True)
def _require_accelerator(backend: str) -> None:  # noqa: ARG001
    """Auto-use fixture: skip the entire test when no accelerator is found."""
    # ``backend`` already calls pytest.skip when _BACKEND is None.
    pass
