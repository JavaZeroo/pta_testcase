"""CLI backend abstraction layer for AI coding agents."""

from __future__ import annotations

from scripts.backends.base import CliBackend
from scripts.backends.claude import ClaudeBackend
from scripts.backends.codex import CodexBackend
from scripts.backends.copilot import CopilotBackend

SUPPORTED_BACKENDS = {"codex", "copilot", "claude"}


def get_backend(name: str) -> CliBackend:
    """Return a *CliBackend* instance by identifier.

    Supported values: ``"codex"``, ``"copilot"``, ``"claude"``.
    """
    if name == "codex":
        return CodexBackend()
    if name == "copilot":
        return CopilotBackend()
    if name == "claude":
        return ClaudeBackend()
    raise ValueError(
        f"unsupported CLI backend {name!r}; choose from {sorted(SUPPORTED_BACKENDS)}"
    )


__all__ = [
    "CliBackend",
    "ClaudeBackend",
    "CodexBackend",
    "CopilotBackend",
    "SUPPORTED_BACKENDS",
    "get_backend",
]
