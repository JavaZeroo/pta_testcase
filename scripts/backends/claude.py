"""Claude Code CLI backend implementation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from scripts.backends.base import CliBackend

# Override the base command via environment variable, e.g.
#   PTA_CLAUDE_CMD="claude"
_CLAUDE_CMD = os.environ.get("PTA_CLAUDE_CMD", "claude")

# Default session log directory
_DEFAULT_LOG_DIR = Path.home() / ".claude" / "projects"


class ClaudeBackend(CliBackend):

    @property
    def name(self) -> str:
        return "claude"

    def exec_prompt(
        self,
        prompt: str,
        *,
        summary_path: Path,
        stdout_path: Path,
        stderr_path: Path,
        cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        base_cmd = _CLAUDE_CMD.split()

        summary_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            *base_cmd,
            "-p",               # print mode (non-interactive, outputs result to stdout)
            prompt,
            "--permission-mode", "acceptEdits",
            "--no-session-persistence",
        ]

        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )

        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text(completed.stderr, encoding="utf-8")

        # Claude Code outputs its response to stdout in print mode.
        # Save stdout as the summary (equivalent to Codex --output-last-message).
        summary_path.write_text(completed.stdout, encoding="utf-8")

        return completed

    # ---- configuration directories ----

    @property
    def repo_config_dir(self) -> str:
        return ".claude"

    @property
    def agents_dir(self) -> str:
        return ".claude/agents"

    @property
    def skills_dir(self) -> str:
        return ".claude/commands"

    # ---- session logs ----

    @property
    def session_log_dir(self) -> Path | None:
        return _DEFAULT_LOG_DIR if _DEFAULT_LOG_DIR.exists() else None
