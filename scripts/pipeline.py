from __future__ import annotations

import argparse
import csv
import json
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from scripts.backends import CliBackend, SUPPORTED_BACKENDS, get_backend


ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = ROOT / "test" / "api_test"
RUNS_DIR = ROOT / "runs"
DEFAULT_MANIFEST_FIELDS = ["raw_api_name", "canonical_name", "file_name", "status", "notes"]
RUN_MANIFEST_FIELDS = DEFAULT_MANIFEST_FIELDS + [
    "selected_for_run",
    "run_phase",
    "stage",
    "test_file_exists",
    "final_status",
    "pytest_outcome",
    "failure_category",
    "root_cause_summary",
    "tests_total",
    "passed_count",
    "skipped_count",
    "xfailed_count",
    "failed_count",
    "error_count",
    "fix_recommendation",
    "auto_fixable",
    "fix_applied",
    "fix_target",
    "rerun_status",
    "changed_files",
    "fix_artifact",
    "report_path",
    "intervention_type",
    "intervention_reason",
    "last_updated_utc",
]
FIX_MODES = {"off", "tests", "safe"}
RUN_ENGINES = {"local", "agent"}
ANALYSIS_ENGINES = {"heuristic", "agent"}
FAILURE_CATEGORIES = {
    "NONE",
    "TEST_BUG",
    "UNSUPPORTED_ON_NPU",
    "SKIP_HEAVY",
    "ENVIRONMENT_MISSING",
    "API_BEHAVIOR_MISMATCH",
    "PYTORCH_BUG",
    "TORCH_NPU_BUG",
    "OPERATOR_BUG",
    "FLAKY_OR_UNSTABLE",
    "INSUFFICIENT_COVERAGE",
    "NOT_COLLECTED",
    "UNKNOWN",
}


@dataclass
class ManifestEntry:
    raw_api_name: str
    canonical_name: str
    file_name: str
    status: str = "pending"
    notes: str = ""

    @property
    def test_path(self) -> Path:
        return TEST_DIR / self.file_name


@dataclass
class ApiResult:
    raw_api_name: str
    canonical_name: str
    file_name: str
    stage: str = "manifest"
    final_status: str = "pending"
    pytest_outcome: str = "not_run"
    failure_category: str = "UNKNOWN"
    root_cause_summary: str = ""
    initial_failure_category: str = "UNKNOWN"
    initial_root_cause_summary: str = ""
    failure_messages: list[str] = field(default_factory=list)
    tests_total: int = 0
    passed_count: int = 0
    skipped_count: int = 0
    xfailed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    fix_recommendation: str = "none"
    auto_fixable: bool = False
    fix_applied: bool = False
    fix_target: str = ""
    fix_summary: str = ""
    fix_artifact: str = ""
    changed_files: list[str] = field(default_factory=list)
    rerun_status: str = "not_run"
    report_path: str = ""
    intervention_type: str = ""
    intervention_reason: str = ""


class PipelineLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        line = f"[{timestamp}] {message}"
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def api_to_filename(api_name: str) -> str:
    name = api_name.strip()
    if not name:
        return ""
    if name.startswith("torch."):
        name = name[len("torch.") :]
    return f"test_{name.replace('.', '_')}.py"


def build_manifest_from_text_input(input_path: Path, output_path: Path) -> list[ManifestEntry]:
    rows: list[ManifestEntry] = []
    for line in input_path.read_text(encoding="utf-8").splitlines():
        api_name = line.strip()
        if not api_name or api_name.startswith("#"):
            continue
        rows.append(
            ManifestEntry(
                raw_api_name=api_name,
                canonical_name=api_name,
                file_name=api_to_filename(api_name),
                status="pending",
                notes="",
            )
        )
    write_manifest(rows, output_path)
    return rows


def load_manifest(path: Path) -> list[ManifestEntry]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in DEFAULT_MANIFEST_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"manifest missing required fields: {', '.join(missing)}")
        return [
            ManifestEntry(
                raw_api_name=row["raw_api_name"].strip(),
                canonical_name=row["canonical_name"].strip(),
                file_name=row["file_name"].strip(),
                status=(row.get("status") or "pending").strip() or "pending",
                notes=(row.get("notes") or "").strip(),
            )
            for row in reader
            if (row.get("canonical_name") or "").strip()
        ]


def write_manifest(entries: Iterable[ManifestEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEFAULT_MANIFEST_FIELDS)
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "raw_api_name": entry.raw_api_name,
                    "canonical_name": entry.canonical_name,
                    "file_name": entry.file_name,
                    "status": entry.status,
                    "notes": entry.notes,
                }
            )


def csv_bool(value: bool) -> str:
    return "yes" if value else "no"


def csv_json(value: object) -> str:
    if value in ("", None, [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False)


def derive_run_manifest_status(
    entry: ManifestEntry,
    *,
    selected: bool,
    run_phase: str,
    result: ApiResult | None,
) -> str:
    if result is not None:
        return result.final_status
    if not selected:
        return entry.status
    if run_phase == "queued":
        return entry.status
    if run_phase in {"generated", "reused_existing"}:
        return "generated" if entry.test_path.exists() else "generation_missing"
    return entry.status


def write_run_manifest(
    entries: list[ManifestEntry],
    path: Path,
    *,
    selected_entries: list[ManifestEntry],
    run_phase: str,
    results: list[ApiResult] | None = None,
) -> None:
    selected_names = {entry.canonical_name for entry in selected_entries}
    results_by_name = {result.canonical_name: result for result in (results or [])}
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=RUN_MANIFEST_FIELDS)
        writer.writeheader()
        for entry in entries:
            selected = entry.canonical_name in selected_names
            result = results_by_name.get(entry.canonical_name)
            writer.writerow(
                {
                    "raw_api_name": entry.raw_api_name,
                    "canonical_name": entry.canonical_name,
                    "file_name": entry.file_name,
                    "status": derive_run_manifest_status(entry, selected=selected, run_phase=run_phase, result=result),
                    "notes": entry.notes,
                    "selected_for_run": csv_bool(selected),
                    "run_phase": run_phase,
                    "stage": result.stage if result is not None else ("manifest" if selected else "deferred"),
                    "test_file_exists": csv_bool(entry.test_path.exists()),
                    "final_status": result.final_status if result is not None else "",
                    "pytest_outcome": result.pytest_outcome if result is not None else "",
                    "failure_category": result.failure_category if result is not None else "",
                    "root_cause_summary": result.root_cause_summary if result is not None else "",
                    "tests_total": result.tests_total if result is not None else "",
                    "passed_count": result.passed_count if result is not None else "",
                    "skipped_count": result.skipped_count if result is not None else "",
                    "xfailed_count": result.xfailed_count if result is not None else "",
                    "failed_count": result.failed_count if result is not None else "",
                    "error_count": result.error_count if result is not None else "",
                    "fix_recommendation": result.fix_recommendation if result is not None else "",
                    "auto_fixable": csv_bool(result.auto_fixable) if result is not None else "",
                    "fix_applied": csv_bool(result.fix_applied) if result is not None else "",
                    "fix_target": result.fix_target if result is not None else "",
                    "rerun_status": result.rerun_status if result is not None else "",
                    "changed_files": csv_json(result.changed_files) if result is not None else "",
                    "fix_artifact": result.fix_artifact if result is not None else "",
                    "report_path": result.report_path if result is not None else "",
                    "intervention_type": result.intervention_type if result is not None else "",
                    "intervention_reason": result.intervention_reason if result is not None else "",
                    "last_updated_utc": timestamp,
                }
            )


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_run_dir(report_dir: Path | None, resume_dir: Path | None) -> Path:
    if resume_dir is not None:
        run_dir = resume_dir.resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    base_dir = (report_dir or RUNS_DIR).resolve()
    run_dir = base_dir / utc_run_id()
    suffix = 1
    while run_dir.exists():
        run_dir = base_dir / f"{utc_run_id()}_{suffix}"
        suffix += 1
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_command(
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    stdin_text: str | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        input=stdin_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if stdout_path is not None:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
    if stderr_path is not None:
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text(completed.stderr, encoding="utf-8")
    return completed


def run_agent_exec(
    backend: CliBackend,
    prompt: str,
    *,
    summary_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    """Execute a prompt through the configured CLI backend."""
    return backend.exec_prompt(
        prompt,
        summary_path=summary_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        cwd=cwd,
    )


def collect_session_logs(
    backend: CliBackend,
    since: float,
    dest_dir: Path,
    logger: PipelineLogger | None = None,
) -> int:
    """Copy session log files produced since *since* (epoch time) into *dest_dir*.

    Collects .log, .jsonl, and .json files from the backend's session log
    directory.  Returns the number of files copied.
    """
    log_dir = backend.session_log_dir
    if log_dir is None or not log_dir.exists():
        return 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for pattern in ("*.log", "*.jsonl", "*.json"):
        for log_file in log_dir.rglob(pattern):
            if log_file.is_file() and log_file.stat().st_mtime >= since:
                shutil.copy2(log_file, dest_dir / log_file.name)
                count += 1
    if logger and count:
        logger.log(f"agent_logs collected={count} dir={relative_to_root(dest_dir)}")
    return count


def relative_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def resolve_input_manifest(input_path: Path, run_dir: Path) -> tuple[list[ManifestEntry], Path]:
    suffix = input_path.suffix.lower()
    if suffix == ".txt":
        manifest_path = run_dir / "manifest.csv"
        entries = build_manifest_from_text_input(input_path.resolve(), manifest_path)
        return entries, manifest_path
    if suffix == ".csv":
        manifest_path = run_dir / "manifest.csv"
        entries = load_manifest(input_path.resolve())
        write_manifest(entries, manifest_path)
        return entries, manifest_path
    raise ValueError(f"unsupported input type for {input_path}; expected .txt or .csv")


def prompt_for_generation(manifest_path: Path, run_dir: Path, max_workers: int, context_dir: Path | None = None) -> str:
    context_section = ""
    if context_dir is not None and context_dir.exists():
        ctx_path = relative_to_root(context_dir)
        context_section = (
            f"8. 每个 API 在 {ctx_path}/ 下有一个同名 JSON 上下文文件（文件名为\n"
            f"   canonical_name 中的 `.` 替换为 `_`，后缀 `.json`）。\n"
            f"   上下文文件包含该 API 的文档签名、参数说明、示例代码，以及 PyTorch 上游的参考测试片段。\n"
            f"   生成器子代理在生成测试前必须读取对应的上下文文件，并据此决定参数覆盖维度和测试策略。\n"
        )
    lines = [
        f"使用 batch-npu-api-test skill。",
        f"",
        f"处理 CSV 文件：{relative_to_root(manifest_path)}",
        f"",
        f"执行生成阶段，不要把任务拆成需要我再次确认的多轮对话。",
        f"要求：",
        f"1. 只读取 CSV 中 status=pending 的 API。",
        f"2. 启动 generator/reviewer 并行生成和审查测试文件。",
        f"3. 可以对测试文件做最小修复，但只允许修改 test/api_test/ 下 CSV 对应的目标文件，且禁止使用 pytest.xfail。",
        f"4. 不要运行 pytest；外层 pipeline 会统一执行和分析。",
        f"5. 不要修改其他目录。",
        f"6. 最终回复写入简洁的生成摘要，包含触达的文件和静态阻塞项。",
        f"7. 本次批处理的并发预算参考值：{max_workers}。",
        f"8. 生成功能测试时以正常可调用路径为主，优先验证 API 能否在 NPU 上正常运行、返回类型是否合理、输出设备行为是否正确。",
        f"9. 不要生成过多报错导向用例；只有在上下文或文档明确表明会稳定抛异常时，才保留少量高价值 pytest.raises 场景。",
        f"10. 不要为了凑覆盖机械地写 `None`、`object()`、`int` 等无意义负例；避免产出 `DID NOT RAISE TypeError` 这一类脆弱测试。",
    ]
    if context_section:
        lines.append(context_section)
    lines.extend([
        f"",
        f"生成摘要请写到最终消息。外层 pipeline 会保存到：",
        f"{relative_to_root(run_dir / 'generation_summary.md')}",
    ])
    return "\n".join(lines) + "\n"


def run_context_extraction_stage(
    manifest_path: Path,
    run_dir: Path,
    logger: PipelineLogger | None = None,
) -> Path:
    """Build API context files (doc + test references) for all pending APIs.

    Returns the context directory path.
    """
    context_dir = run_dir / "api_context"
    started = time.monotonic()
    if logger is not None:
        logger.log(
            "stage=context_extraction start "
            f"manifest={relative_to_root(manifest_path)} "
            f"output_dir={relative_to_root(context_dir)}"
        )
    cmd = [
        sys.executable, "-m", "scripts.build_api_context",
        "--manifest", str(manifest_path),
        "--output-dir", str(context_dir),
        "--all-status",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if logger is not None:
        logger.log(
            "stage=context_extraction done "
            f"returncode={result.returncode} elapsed_s={time.monotonic() - started:.1f} "
            f"context_dir={relative_to_root(context_dir)}"
        )
    if result.returncode != 0:
        # Non-fatal: log warning but continue
        if logger is not None:
            logger.log(f"stage=context_extraction warning stderr={result.stderr[:500]}")
    return context_dir


def run_generation_stage(
    manifest_path: Path,
    run_dir: Path,
    max_workers: int,
    backend: CliBackend,
    logger: PipelineLogger | None = None,
    context_dir: Path | None = None,
) -> None:
    started = time.monotonic()
    if logger is not None:
        logger.log(
            "stage=generation start "
            f"manifest={relative_to_root(manifest_path)} max_workers={max_workers} "
            f"backend={backend.name} "
            f"stdout={relative_to_root(run_dir / 'agent_generation.stdout.log')} "
            f"stderr={relative_to_root(run_dir / 'agent_generation.stderr.log')}"
        )
    prompt = prompt_for_generation(manifest_path, run_dir, max_workers, context_dir=context_dir)
    completed = run_agent_exec(
        backend,
        prompt,
        summary_path=run_dir / "generation_summary.md",
        stdout_path=run_dir / "agent_generation.stdout.log",
        stderr_path=run_dir / "agent_generation.stderr.log",
    )
    if logger is not None:
        logger.log(
            "stage=generation done "
            f"returncode={completed.returncode} elapsed_s={time.monotonic() - started:.1f} "
            f"summary={relative_to_root(run_dir / 'generation_summary.md')}"
        )
    if completed.returncode != 0:
        raise RuntimeError(
            "generation stage failed; inspect "
            f"{relative_to_root(run_dir / 'agent_generation.stderr.log')}"
        )


def build_pytest_command(test_files: list[Path], junit_path: Path) -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", "--junitxml", str(junit_path), *[str(path) for path in test_files]]


def prompt_for_execution(
    label: str,
    pytest_cmd: str,
    command_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    returncode_path: Path,
) -> str:
    command_file = shlex.quote(str(command_path))
    stdout_file = shlex.quote(str(stdout_path))
    stderr_file = shlex.quote(str(stderr_path))
    returncode_file = shlex.quote(str(returncode_path))
    parent_dir = shlex.quote(str(stdout_path.parent))
    shell_script = textwrap.dedent(
        f"""\
        mkdir -p {parent_dir}
        cat <<'EOF' > {command_file}
        {pytest_cmd}
        EOF
        set +e
        {pytest_cmd} > {stdout_file} 2> {stderr_file}
        status=$?
        printf '%s\\n' "$status" > {returncode_file}
        exit 0
        """
    ).strip()
    return textwrap.dedent(
        f"""\
        执行 pytest 阶段，不要修改任何源码、测试文件或文档。

        阶段标签: {label}
        你必须运行下面这段 bash 脚本，完整保留 pytest 的 stdout/stderr 和 return code。

        ```bash
        {shell_script}
        ```

        要求：
        1. 只执行上面的脚本，不要额外改文件。
        2. 即使 pytest 失败，也不要把这次任务判成失败；保留日志即可。
        3. 最终回复只写简洁总结，包含 return code 和产物路径。
        """
    )


def run_pytest_stage(
    test_files: list[Path],
    run_dir: Path,
    label: str,
    engine: str,
    backend: CliBackend | None = None,
    logger: PipelineLogger | None = None,
) -> dict[str, object]:
    junit_path = run_dir / "pytest_raw" / f"{label}_junit.xml"
    stdout_path = run_dir / "pytest_raw" / f"{label}.stdout.log"
    stderr_path = run_dir / "pytest_raw" / f"{label}.stderr.log"
    command_path = run_dir / "pytest_raw" / f"{label}.command.txt"
    returncode_path = run_dir / "pytest_raw" / f"{label}.returncode.txt"
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    if logger is not None:
        logger.log(
            "stage=pytest start "
            f"label={label} engine={engine} test_files={len(test_files)} "
            f"stdout={relative_to_root(stdout_path)} stderr={relative_to_root(stderr_path)} "
            f"junit={relative_to_root(junit_path)}"
        )

    if not test_files:
        junit_path.write_text("<testsuite tests=\"0\" failures=\"0\" errors=\"0\" skipped=\"0\" />\n", encoding="utf-8")
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        command_text = "(pytest skipped: no target files existed)"
        command_path.write_text(command_text, encoding="utf-8")
        returncode_path.write_text("0\n", encoding="utf-8")
        if logger is not None:
            logger.log(f"stage=pytest done label={label} returncode=0 elapsed_s={time.monotonic() - started:.1f} skipped_no_files=true")
        return {
            "returncode": 0,
            "junit_path": junit_path,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "command": command_text,
        }

    cmd = build_pytest_command(test_files, junit_path)
    command_text = " ".join(shlex.quote(part) for part in cmd)
    if engine == "local":
        completed = run_command(cmd, cwd=ROOT, stdout_path=stdout_path, stderr_path=stderr_path)
        command_path.write_text(command_text, encoding="utf-8")
        returncode_path.write_text(f"{completed.returncode}\n", encoding="utf-8")
        if logger is not None:
            logger.log(
                f"stage=pytest done label={label} returncode={completed.returncode} "
                f"elapsed_s={time.monotonic() - started:.1f}"
            )
        return {
            "returncode": completed.returncode,
            "junit_path": junit_path,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "command": command_text,
        }

    prompt = prompt_for_execution(
        label,
        command_text,
        command_path,
        stdout_path,
        stderr_path,
        returncode_path,
    )
    if backend is None:
        raise RuntimeError("run_pytest_stage requires a backend when engine='agent'")
    completed = run_agent_exec(
        backend,
        prompt,
        summary_path=run_dir / "pytest_raw" / f"{label}.agent.md",
        stdout_path=run_dir / "pytest_raw" / f"{label}.agent.stdout.log",
        stderr_path=run_dir / "pytest_raw" / f"{label}.agent.stderr.log",
    )
    if completed.returncode != 0:
        # Agent failed (quota exhausted, network error, etc.) – fall back to local execution
        if logger is not None:
            logger.log(
                f"stage=pytest agent_fallback label={label} "
                f"reason=agent_rc={completed.returncode} falling_back_to_local"
            )
        completed_local = run_command(cmd, cwd=ROOT, stdout_path=stdout_path, stderr_path=stderr_path)
        command_path.write_text(command_text, encoding="utf-8")
        returncode_path.write_text(f"{completed_local.returncode}\n", encoding="utf-8")
        if logger is not None:
            logger.log(
                f"stage=pytest done label={label} returncode={completed_local.returncode} "
                f"elapsed_s={time.monotonic() - started:.1f} engine=local_fallback"
            )
        return {
            "returncode": completed_local.returncode,
            "junit_path": junit_path,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "command": command_text,
        }
    if not returncode_path.exists():
        # Agent finished but didn't write returncode – fall back to local execution
        if logger is not None:
            logger.log(
                f"stage=pytest agent_fallback label={label} "
                f"reason=no_returncode_file falling_back_to_local"
            )
        completed_local = run_command(cmd, cwd=ROOT, stdout_path=stdout_path, stderr_path=stderr_path)
        command_path.write_text(command_text, encoding="utf-8")
        returncode_path.write_text(f"{completed_local.returncode}\n", encoding="utf-8")
        if logger is not None:
            logger.log(
                f"stage=pytest done label={label} returncode={completed_local.returncode} "
                f"elapsed_s={time.monotonic() - started:.1f} engine=local_fallback"
            )
        return {
            "returncode": completed_local.returncode,
            "junit_path": junit_path,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "command": command_text,
        }
    returncode = int(returncode_path.read_text(encoding="utf-8").strip() or "1")
    if logger is not None:
        logger.log(
            f"stage=pytest done label={label} returncode={returncode} "
            f"elapsed_s={time.monotonic() - started:.1f} "
            f"agent_summary={relative_to_root(run_dir / 'pytest_raw' / f'{label}.agent.md')}"
        )
    return {
        "returncode": returncode,
        "junit_path": junit_path,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "command": command_text,
    }


def parse_testcase_outcome(testcase: ET.Element) -> tuple[str, str]:
    failure = testcase.find("failure")
    if failure is not None:
        return "failed", build_message_blob(failure)
    error = testcase.find("error")
    if error is not None:
        return "error", build_message_blob(error)
    skipped = testcase.find("skipped")
    if skipped is not None:
        message = build_message_blob(skipped)
        kind = (skipped.attrib.get("type") or "").lower()
        if "xfail" in kind or "xfail" in message.lower():
            return "xfailed", message
        return "skipped", message
    return "passed", ""


def build_message_blob(node: ET.Element) -> str:
    parts = [node.attrib.get("message", "").strip(), (node.text or "").strip()]
    return "\n".join(part for part in parts if part).strip()


def resolve_entry_for_testcase(testcase: ET.Element, by_stem: dict[str, ManifestEntry]) -> ManifestEntry | None:
    file_attr = testcase.attrib.get("file", "")
    classname = testcase.attrib.get("classname", "")
    name = testcase.attrib.get("name", "")
    candidates = [file_attr, classname, name]
    best_match: ManifestEntry | None = None
    best_length = -1
    for candidate in candidates:
        normalized = candidate.replace("\\", "/")
        for stem, entry in by_stem.items():
            if (stem in normalized or entry.file_name in normalized) and len(stem) > best_length:
                best_match = entry
                best_length = len(stem)
    return best_match


def parse_junit_results(
    entries: list[ManifestEntry],
    execution: dict[str, object],
) -> dict[str, dict[str, object]]:
    per_api: dict[str, dict[str, object]] = {
        entry.canonical_name: {
            "tests_total": 0,
            "passed_count": 0,
            "skipped_count": 0,
            "xfailed_count": 0,
            "failed_count": 0,
            "error_count": 0,
            "messages": [],
        }
        for entry in entries
    }

    by_stem = {Path(entry.file_name).stem: entry for entry in entries}
    junit_path = execution["junit_path"]
    if not Path(junit_path).exists():
        return per_api

    tree = ET.parse(junit_path)
    root = tree.getroot()
    for testcase in root.iter("testcase"):
        entry = resolve_entry_for_testcase(testcase, by_stem)
        if entry is None:
            continue
        bucket = per_api[entry.canonical_name]
        outcome, message = parse_testcase_outcome(testcase)
        bucket["tests_total"] += 1
        if outcome == "passed":
            bucket["passed_count"] += 1
        elif outcome == "skipped":
            bucket["skipped_count"] += 1
        elif outcome == "xfailed":
            bucket["xfailed_count"] += 1
        elif outcome == "failed":
            bucket["failed_count"] += 1
        elif outcome == "error":
            bucket["error_count"] += 1
        if message:
            bucket["messages"].append(message)
    return per_api


def first_non_empty(items: Iterable[str]) -> str:
    for item in items:
        if item:
            return item
    return ""


def derive_final_status(bucket: dict[str, object], entry: ManifestEntry) -> tuple[str, str]:
    if not entry.test_path.exists():
        return "review_failed", "not_collected"
    failed = int(bucket["failed_count"])
    errors = int(bucket["error_count"])
    passed = int(bucket["passed_count"])
    skipped = int(bucket["skipped_count"])
    xfailed = int(bucket["xfailed_count"])
    if failed or errors or xfailed:
        if xfailed and not failed and not errors:
            return "pytest_failed", "xfailed_not_allowed"
        return "pytest_failed", "failed"
    if passed:
        if skipped:
            # skip_heavy: too many skips relative to passed tests
            if skipped > passed and skipped >= 2:
                return "skip_heavy", "skip_heavy"
            return "pytest_passed", "passed_with_skips"
        return "pytest_passed", "passed"
    if skipped:
        return "skipped", "skipped"
    return "analyzed", "no_tests_recorded"


def detect_category(text: str, final_status: str) -> str:
    lowered = text.lower()
    if final_status in {"pytest_passed", "fixed"}:
        return "NONE"
    if "pytest.xfail" in lowered or "xfail" in lowered:
        return "TEST_BUG"
    if any(token in lowered for token in ["torch_npu import failed", "no module named 'torch_npu'", "npu is not available"]):
        return "ENVIRONMENT_MISSING"
    if any(token in lowered for token in ["not supported by this npu backend", "unsupported on npu", "does not support", "not exposed in this build", "dispatchkey.npu"]):
        return "UNSUPPORTED_ON_NPU"
    if any(token in lowered for token in ["not reliable", "unstable", "flaky"]):
        return "FLAKY_OR_UNSTABLE"
    if any(token in lowered for token in ["aclnn", "aclop", "op api", "opapi", "op-plugin", "kernel", "operator"]):
        return "OPERATOR_BUG"
    if any(token in lowered for token in ["/ascend-pytorch/", "torch_npu/"]):
        return "TORCH_NPU_BUG"
    if any(token in lowered for token in ["/pytorch/", " aten/", "torch/csrc", "c10/"]):
        return "PYTORCH_BUG"
    if any(token in lowered for token in ["did not raise", "assertionerror", "typeerror", "attributeerror", "nameerror", "runtimeerror"]) and "test/api_test" in lowered:
        return "TEST_BUG"
    if "coverage" in lowered and any(token in lowered for token in ["missing", "insufficient", "uncovered"]):
        return "INSUFFICIENT_COVERAGE"
    if final_status == "analyzed":
        return "NOT_COLLECTED"
    if final_status == "skip_heavy":
        return "SKIP_HEAVY"
    if final_status == "skipped":
        return "UNSUPPORTED_ON_NPU"
    if final_status == "pytest_failed":
        return "API_BEHAVIOR_MISMATCH"
    return "UNKNOWN"


def recommend_fix(category: str, fix_mode: str) -> tuple[str, bool, str]:
    if fix_mode == "off":
        return "manual_followup", False, ""
    if category in {"TEST_BUG", "SKIP_HEAVY"}:
        return "adjust_test", True, "test/api_test"
    if category in {"ENVIRONMENT_MISSING", "UNSUPPORTED_ON_NPU", "FLAKY_OR_UNSTABLE", "INSUFFICIENT_COVERAGE", "OPERATOR_BUG"}:
        return "manual_followup", False, ""
    if fix_mode == "safe" and category == "PYTORCH_BUG":
        return "patch_pytorch", True, "pytorch"
    if fix_mode == "safe" and category == "TORCH_NPU_BUG":
        return "patch_torch_npu", True, "ascend-pytorch"
    if fix_mode == "safe" and category == "API_BEHAVIOR_MISMATCH":
        return "manual_followup", False, ""
    return "manual_followup", False, ""


# Mapping from failure category to a short intervention reason code used by
# derive_intervention_type.  Defined at module level to avoid repeated creation.
_CATEGORY_REASON_MAP: dict[str, str] = {
    "UNSUPPORTED_ON_NPU": "api_not_supported_on_npu",
    "SKIP_HEAVY": "skip_heavy",
    "ENVIRONMENT_MISSING": "environment_setup_required",
    "PYTORCH_BUG": "pytorch_source_bug",
    "TORCH_NPU_BUG": "torch_npu_source_bug",
    "OPERATOR_BUG": "operator_level_bug",
    "API_BEHAVIOR_MISMATCH": "api_behavior_mismatch",
    "FLAKY_OR_UNSTABLE": "flaky_or_unstable_test",
    "INSUFFICIENT_COVERAGE": "insufficient_test_coverage",
    "NOT_COLLECTED": "tests_not_collected",
    "TEST_BUG": "test_bug_fix_failed",
}


def derive_intervention_type(result: ApiResult) -> tuple[str, str]:
    """Return (intervention_type, intervention_reason) for a fully-processed result.

    intervention_type values:
      - "none"           : pipeline completed successfully; no action required.
      - "agent_retry"    : AI agent can plausibly address this without human help.
      - "human_required" : needs human investigation and/or manual fix.

    intervention_reason is a short snake_case code explaining the specific cause.
    """
    # All-clear: passed or successfully fixed by auto-fix
    if result.final_status in {"pytest_passed", "fixed"}:
        return "none", ""

    # skip_heavy: too many skips — test should be regenerated with fewer skips
    if result.final_status == "skip_heavy":
        if result.fix_applied and result.rerun_status not in {"pytest_passed", "fixed", "not_run"}:
            return "human_required", "skip_heavy_fix_failed"
        return "agent_retry", "skip_heavy"

    # Test file was never generated/collected → regeneration is worth trying
    if result.final_status == "review_failed" and result.pytest_outcome in {"not_generated", "not_collected"}:
        return "agent_retry", "test_not_generated"

    # Tests existed but were not collected by pytest → retry
    if result.failure_category == "NOT_COLLECTED":
        return "agent_retry", "tests_not_collected"

    # Test has a TEST_BUG but fix was not yet applied → auto-fix can be attempted
    if result.failure_category == "TEST_BUG" and not result.fix_applied:
        return "agent_retry", "test_bug_not_yet_fixed"

    # Agent tried a fix but the rerun still failed → escalate to human
    if result.fix_applied and result.rerun_status not in {"pytest_passed", "fixed", "not_run"}:
        return "human_required", "fix_attempted_but_failed"

    reason = _CATEGORY_REASON_MAP.get(result.failure_category, "unknown_failure")
    return "human_required", reason


def annotate_intervention_types(results: list[ApiResult]) -> list[ApiResult]:
    """Set intervention_type / intervention_reason on every result in-place.

    Modifies the list elements in-place and returns the same list for call-site
    chaining convenience.
    """
    for result in results:
        result.intervention_type, result.intervention_reason = derive_intervention_type(result)
    return results


def create_results(entries: list[ManifestEntry], execution: dict[str, object], run_dir: Path, fix_mode: str) -> list[ApiResult]:
    junit_results = parse_junit_results(entries, execution)
    results: list[ApiResult] = []
    for entry in entries:
        bucket = junit_results[entry.canonical_name]
        final_status, pytest_outcome = derive_final_status(bucket, entry)
        message = first_non_empty(bucket["messages"]) or entry.notes
        category = detect_category(message, final_status)
        recommendation, auto_fixable, fix_target = recommend_fix(category, fix_mode)
        skip_heavy_msg = (
            f"skip 数量({int(bucket['skipped_count'])}) > passed 数量({int(bucket['passed_count'])})，"
            "过多 skip 不计入通过。应移除功能性 pytest.skip，让 NPU 不支持的测试自然失败。"
        )
        if final_status == "skip_heavy":
            summary = message or skip_heavy_msg
        elif final_status in {"pytest_passed", "fixed"}:
            summary = message or "全部测试通过。"
        else:
            summary = message or "未捕获到明确的失败详情。"
        result = ApiResult(
            raw_api_name=entry.raw_api_name,
            canonical_name=entry.canonical_name,
            file_name=entry.file_name,
            stage="analysis",
            final_status=final_status,
            pytest_outcome=pytest_outcome,
            failure_category=category,
            root_cause_summary=summary,
            initial_failure_category=category,
            initial_root_cause_summary=summary,
            failure_messages=list(bucket["messages"]),
            tests_total=int(bucket["tests_total"]),
            passed_count=int(bucket["passed_count"]),
            skipped_count=int(bucket["skipped_count"]),
            xfailed_count=int(bucket["xfailed_count"]),
            failed_count=int(bucket["failed_count"]),
            error_count=int(bucket["error_count"]),
            fix_recommendation=recommendation,
            auto_fixable=auto_fixable,
            fix_target=fix_target,
            report_path=relative_to_root(run_dir / "summary.md"),
        )
        if result.failure_category not in FAILURE_CATEGORIES:
            result.failure_category = "UNKNOWN"
        results.append(result)
    return results


def build_analysis_inputs(results: list[ApiResult], run_dir: Path, execution: dict[str, object]) -> Path:
    analysis_items = []
    for result in results:
        if result.final_status not in {"pytest_failed", "skipped", "review_failed", "analyzed", "skip_heavy"}:
            continue
        analysis_items.append(
            {
                "canonical_name": result.canonical_name,
                "file_name": result.file_name,
                "test_path": relative_to_root(TEST_DIR / result.file_name),
                "final_status": result.final_status,
                "pytest_outcome": result.pytest_outcome,
                "heuristic_failure_category": result.failure_category,
                "heuristic_summary": result.root_cause_summary,
                "failure_messages": result.failure_messages,
            }
        )

    payload = {
        "run_dir": relative_to_root(run_dir),
        "generation_summary": relative_to_root(run_dir / "generation_summary.md"),
        "execution_artifacts": {
            "junit_path": relative_to_root(Path(execution["junit_path"])),
            "stdout_path": relative_to_root(Path(execution["stdout_path"])),
            "stderr_path": relative_to_root(Path(execution["stderr_path"])),
            "command": execution["command"],
        },
        "failure_taxonomy": relative_to_root(ROOT / "docs" / "failure_taxonomy.md"),
        "items": analysis_items,
    }
    path = run_dir / "analysis_inputs.json"
    write_json(path, payload)
    return path


def prompt_for_analysis(analysis_input_path: Path, triage_path: Path) -> str:
    categories = ", ".join(sorted(FAILURE_CATEGORIES - {"NONE"}))
    return textwrap.dedent(
        f"""\
        执行失败分诊阶段，不要修改任何源码、测试文件或文档。

        输入文件：
        - 分析输入：{relative_to_root(analysis_input_path)}
        - 分类规则：{relative_to_root(ROOT / 'docs' / 'failure_taxonomy.md')}

        任务：
        1. 读取 analysis_inputs.json 中的所有失败/skip/review_failed/skip_heavy API。
        2. **必须**查看对应的测试文件源码和 pytest 日志，深入分析失败根因。
        3. 为每个 API 产出一条 JSON 记录，写入 {relative_to_root(triage_path)}。

        ## 核心分类原则

        每个失败必须归入以下四大类之一（映射到具体 category 值）：

        **1. 用例问题（TEST_BUG）** — 测试代码本身有错，**必须被后续流程修复**：
        - `DID NOT RAISE`：测试用 pytest.raises 期望异常，但 PyTorch 实际不抛。
          判断方法：查看 PyTorch 源码或文档，确认该 API 是否真的会对该输入校验并抛异常。
          大多数 PyTorch API 对 None/非callable 等非法参数**不做校验**，直接接受。
        - 断言值错误：如 device('npu', 0) != device('npu')、isinstance 检查失败。
        - 测试构造错误：如 int dtype 的 Parameter、传 None 给要求 Tensor 的函数。
        - regex match 不匹配实际错误消息。

        **2. torch/torch_npu 问题（PYTORCH_BUG / TORCH_NPU_BUG / OPERATOR_BUG）**：
        - NPU operator 不支持某 memory format / layout
        - torch_npu 适配层 bug
        - PyTorch 框架本身的 bug
        → 测试逻辑是正确的，但框架/环境有问题。保持失败。

        **3. 环境问题（ENVIRONMENT_MISSING）**：
        - torch_npu 未安装、NPU 不可用

        **4. 未知问题（UNKNOWN / API_BEHAVIOR_MISMATCH）**：
        - 无法确定属于用例问题还是框架问题时使用

        ## 关于 DID NOT RAISE 的深入判断

        当你看到 `Failed: DID NOT RAISE <SomeException>` 时：
        - 查看测试代码中 pytest.raises 块的具体内容
        - 分析传入的参数（如 None、int、object()）
        - 判断：PyTorch 是否应该对这种输入抛异常？
        - 如果 PyTorch 文档/源码没有说明会抛异常 → **标记为 TEST_BUG**
        - 如果 PyTorch 文档明确说会抛异常但没抛 → **标记为 PYTORCH_BUG**

        输出 JSON 必须是数组，每一项严格包含：
        - canonical_name
        - failure_category
        - root_cause_summary（必须说明是用例问题、框架问题还是环境问题）

        约束：
        1. failure_category 只能取这些值：{categories}
        2. 只有确定是 test/api_test 下用例代码问题时，才标记为 TEST_BUG。
        3. 如果看到 pytest.xfail 或 xfail 痕迹，把它视为测试策略违规，优先标记为 TEST_BUG。
        4. 环境问题、PyTorch 代码问题、torch_npu/ascend-pytorch 问题、底层算子问题要区分开。
        5. 不明确时宁可保守标成 UNKNOWN 或 API_BEHAVIOR_MISMATCH，不要编造证据。
        6. 最终回复只写简洁分析总结。
        """
    )


def load_analysis_triage(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, list):
        return {}
    triage: dict[str, dict[str, str]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        canonical_name = str(item.get("canonical_name", "")).strip()
        category = str(item.get("failure_category", "")).strip()
        summary = str(item.get("root_cause_summary", "")).strip()
        if not canonical_name or category not in FAILURE_CATEGORIES:
            continue
        triage[canonical_name] = {
            "failure_category": category,
            "root_cause_summary": summary,
        }
    return triage


def render_analysis_summary(results: list[ApiResult], run_dir: Path, fix_mode: str) -> str:
    lines = [
        f"# 分析摘要：{run_dir.name}",
        "",
        f"- 修复模式：`{fix_mode}`",
        f"- 输入文件：`{relative_to_root(run_dir / 'analysis_inputs.json')}`",
        f"- 分诊 JSON：`{relative_to_root(run_dir / 'analysis_triage.json')}`",
        f"- AI 代理备注：`{relative_to_root(run_dir / 'analysis_agent.md')}`",
        "",
        "## 可自动修复候选",
    ]
    candidates = [result for result in results if result.auto_fixable and result.final_status in {"pytest_failed", "skipped", "review_failed", "skip_heavy"}]
    if candidates:
        for result in candidates:
            lines.append(
                f"- `{result.canonical_name}`: `{result.failure_category}` -> `{result.fix_recommendation}`; "
                f"{result.root_cause_summary or '无摘要'}"
            )
    else:
        lines.append("- 无")

    lines.extend(["", "## 仅报告（不自动修复）失败"])
    report_only = [result for result in results if not result.auto_fixable and result.final_status in {"pytest_failed", "skipped", "review_failed", "skip_heavy"}]
    if report_only:
        for result in report_only:
            lines.append(
                f"- `{result.canonical_name}`: `{result.failure_category}`; "
                f"{result.root_cause_summary or '无摘要'}"
            )
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def run_analysis_stage(
    results: list[ApiResult],
    run_dir: Path,
    execution: dict[str, object],
    fix_mode: str,
    engine: str,
    backend: CliBackend | None = None,
    logger: PipelineLogger | None = None,
) -> list[ApiResult]:
    started = time.monotonic()
    analysis_input_path = build_analysis_inputs(results, run_dir, execution)
    triage_path = run_dir / "analysis_triage.json"
    agent_notes_path = run_dir / "analysis_agent.md"
    failing_results = [result for result in results if result.final_status in {"pytest_failed", "skipped", "review_failed", "skip_heavy"}]
    if logger is not None:
        logger.log(
            "stage=analysis start "
            f"engine={engine} failing_apis={len(failing_results)} "
            f"inputs={relative_to_root(analysis_input_path)}"
        )
    heuristic_triage = [
        {
            "canonical_name": result.canonical_name,
            "failure_category": result.failure_category,
            "root_cause_summary": result.root_cause_summary,
        }
        for result in failing_results
    ]

    if not failing_results:
        write_json(triage_path, [])
        agent_notes_path.write_text("无需分析的失败 API。\n", encoding="utf-8")
        (run_dir / "analysis_summary.md").write_text(render_analysis_summary(results, run_dir, fix_mode), encoding="utf-8")
        if logger is not None:
            logger.log(
                f"stage=analysis done engine={engine} failing_apis=0 elapsed_s={time.monotonic() - started:.1f} "
                f"summary={relative_to_root(run_dir / 'analysis_summary.md')}"
            )
        return results

    if engine == "agent":
        if backend is None:
            raise RuntimeError("run_analysis_stage requires a backend when engine='agent'")
        prompt = prompt_for_analysis(analysis_input_path, triage_path)
        completed = run_agent_exec(
            backend,
            prompt,
            summary_path=agent_notes_path,
            stdout_path=run_dir / "analysis_agent.stdout.log",
            stderr_path=run_dir / "analysis_agent.stderr.log",
        )
        if completed.returncode == 0:
            triage = load_analysis_triage(triage_path)
            if triage:
                for result in results:
                    item = triage.get(result.canonical_name)
                    if not item:
                        continue
                    result.failure_category = item["failure_category"]
                    result.root_cause_summary = item["root_cause_summary"] or result.root_cause_summary
                    result.initial_failure_category = result.failure_category
                    result.initial_root_cause_summary = result.root_cause_summary
                    result.fix_recommendation, result.auto_fixable, result.fix_target = recommend_fix(result.failure_category, fix_mode)
            else:
                write_json(triage_path, heuristic_triage)
                agent_notes_path.write_text(
                    "AI 代理分析未产生有效的分诊 JSON，已回退至启发式分类。\n",
                    encoding="utf-8",
                )
        else:
            write_json(triage_path, heuristic_triage)
            agent_notes_path.write_text(
                "AI 代理分析失败，已回退至启发式分类。\n",
                encoding="utf-8",
            )
    else:
        write_json(triage_path, heuristic_triage)
        agent_notes_path.write_text("分析引擎=heuristic；未运行嵌套 AI 审查。\n", encoding="utf-8")

    (run_dir / "analysis_summary.md").write_text(render_analysis_summary(results, run_dir, fix_mode), encoding="utf-8")
    if logger is not None:
        logger.log(
            "stage=analysis done "
            f"engine={engine} failing_apis={len(failing_results)} elapsed_s={time.monotonic() - started:.1f} "
            f"summary={relative_to_root(run_dir / 'analysis_summary.md')}"
        )
    return results


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_results(results: list[ApiResult], run_dir: Path) -> None:
    json_path = run_dir / "results.json"
    csv_path = run_dir / "results.csv"
    write_json(json_path, [asdict(result) for result in results])
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()) if results else list(asdict(ApiResult("", "", "")).keys()))
        writer.writeheader()
        for result in results:
            row = asdict(result)
            row["failure_messages"] = json.dumps(result.failure_messages, ensure_ascii=False)
            row["changed_files"] = json.dumps(result.changed_files, ensure_ascii=False)
            writer.writerow(row)


def snapshot_newer_files(paths: list[Path], marker: Path) -> list[str]:
    changed: list[str] = []
    for base in paths:
        if not base.exists():
            continue
        if base.is_file():
            candidates = [base]
        else:
            candidates = [path for path in base.rglob("*") if path.is_file()]
        for candidate in candidates:
            if candidate.stat().st_mtime_ns > marker.stat().st_mtime_ns:
                changed.append(relative_to_root(candidate))
    return sorted(set(changed))


def build_fix_request(result: ApiResult, fix_mode: str) -> dict[str, object]:
    allowed_scopes = [f"test/api_test/{result.file_name}"]
    if fix_mode == "safe":
        allowed_scopes.extend(["pytorch/", "ascend-pytorch/"])
    return {
        "canonical_name": result.canonical_name,
        "file_name": result.file_name,
        "fix_mode": fix_mode,
        "failure_category": result.failure_category,
        "fix_recommendation": result.fix_recommendation,
        "final_status": result.final_status,
        "pytest_outcome": result.pytest_outcome,
        "allowed_scopes": allowed_scopes,
        "root_cause_summary": result.root_cause_summary.strip(),
        "failure_messages": result.failure_messages[:3],
        "passed_count": result.passed_count,
        "skipped_count": result.skipped_count,
        "failed_count": result.failed_count,
    }


def prompt_for_fix(request_path: Path) -> str:
    return textwrap.dedent(
        f"""\
        使用 single-api-fix skill。

        处理修复请求文件：{relative_to_root(request_path)}

        执行修复阶段，不要等待额外确认。
        要求：
        1. 只修复该请求对应的单个 API。
        2. 严格遵守请求文件中的 allowed_scopes。
        3. 禁止使用 pytest.xfail。
        4. 不要运行 pytest；外层 pipeline 会自动回归验证。
        5. 如果 failure_category 为 SKIP_HEAVY，应移除不当的 pytest.skip 调用——
           NPU 后端不支持的功能应让测试自然失败（RuntimeError/NotImplementedError），
           而非用 skip 跳过。只保留环境检测类 skip（API 不存在、torch_npu 缺失、NPU 不可用）。
        6. 最终回复写简洁修复摘要。
        """
    )


def run_fix_attempt(
    result: ApiResult,
    run_dir: Path,
    fix_mode: str,
    run_engine: str,
    backend: CliBackend,
    logger: PipelineLogger | None = None,
) -> ApiResult:
    started = time.monotonic()
    if logger is not None:
        logger.log(
            "stage=fix start "
            f"api={result.canonical_name} category={result.failure_category} "
            f"target=test/api_test/{result.file_name}"
        )
    marker = run_dir / "fixes" / f"{Path(result.file_name).stem}.before"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    request_path = run_dir / "fixes" / f"{Path(result.file_name).stem}.request.json"
    write_json(request_path, build_fix_request(result, fix_mode))
    prompt = prompt_for_fix(request_path)
    summary_path = run_dir / "fixes" / f"{Path(result.file_name).stem}.md"
    completed = run_agent_exec(
        backend,
        prompt,
        summary_path=summary_path,
        stdout_path=run_dir / "fixes" / f"{Path(result.file_name).stem}.stdout.log",
        stderr_path=run_dir / "fixes" / f"{Path(result.file_name).stem}.stderr.log",
    )
    allowed_paths = [TEST_DIR / result.file_name]
    if fix_mode == "safe":
        allowed_paths.extend([ROOT / "pytorch", ROOT / "ascend-pytorch"])
    changed_files = snapshot_newer_files(allowed_paths, marker)
    result.fix_artifact = relative_to_root(summary_path)
    result.fix_summary = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
    result.fix_applied = completed.returncode == 0 and bool(changed_files)
    result.changed_files = changed_files
    if any(path.startswith("pytorch/") for path in changed_files):
        result.fix_target = "pytorch"
    elif any(path.startswith("ascend-pytorch/") for path in changed_files):
        result.fix_target = "ascend-pytorch"
    elif changed_files:
        result.fix_target = "test/api_test"
    if completed.returncode != 0 and not result.fix_summary:
        result.fix_summary = "AI 代理修复尝试以非零状态退出，请检查修复日志。"
    if result.fix_applied:
        rerun = run_pytest_stage(
            [TEST_DIR / result.file_name],
            run_dir,
            f"rerun_{Path(result.file_name).stem}",
            run_engine,
            backend,
            logger,
        )
        rerun_results = create_results(
            [ManifestEntry(result.raw_api_name, result.canonical_name, result.file_name)],
            rerun,
            run_dir,
            fix_mode="off",
        )
        rerun_result = rerun_results[0]
        # Skip inflation detection: reject fix if skip count increased
        pre_fix_skips = result.skipped_count
        post_fix_skips = rerun_result.skipped_count
        if post_fix_skips > pre_fix_skips:
            result.fix_applied = False
            result.rerun_status = "skip_inflation"
            result.fix_summary += (
                f"\n⚠️ 修复被拒绝：skip 数量从 {pre_fix_skips} 增加到 {post_fix_skips}。"
                "严禁通过增加 pytest.skip 来假装修复。"
            )
            # Revert the changed test file
            test_file = TEST_DIR / result.file_name
            if test_file.exists():
                subprocess.run(["git", "checkout", str(test_file)], cwd=str(ROOT), capture_output=True)
            if logger is not None:
                logger.log(
                    f"stage=fix skip_inflation api={result.canonical_name} "
                    f"pre={pre_fix_skips} post={post_fix_skips} — fix reverted"
                )
        else:
            result.rerun_status = rerun_result.final_status
    else:
        result.rerun_status = "not_run"
    if logger is not None:
        logger.log(
            "stage=fix done "
            f"api={result.canonical_name} fix_applied={result.fix_applied} "
            f"rerun_status={result.rerun_status} elapsed_s={time.monotonic() - started:.1f} "
            f"artifact={result.fix_artifact or 'none'}"
        )
    return result


def apply_auto_fixes(
    results: list[ApiResult],
    run_dir: Path,
    fix_mode: str,
    run_engine: str,
    backend: CliBackend,
    logger: PipelineLogger | None = None,
) -> list[ApiResult]:
    if fix_mode == "off":
        if logger is not None:
            logger.log("stage=fix skip reason=fix_mode_off")
        return results
    candidates = [
        result
        for result in results
        if result.final_status in {"pytest_failed", "skipped", "review_failed", "skip_heavy"} and result.auto_fixable
    ]
    if logger is not None:
        logger.log(f"stage=fix queue candidates={len(candidates)} fix_mode={fix_mode}")
    updated: list[ApiResult] = []
    for result in results:
        if result.final_status not in {"pytest_failed", "skipped", "review_failed", "skip_heavy"} or not result.auto_fixable:
            updated.append(result)
            continue
        updated.append(run_fix_attempt(result, run_dir, fix_mode, run_engine, backend, logger))
    return updated


def merge_final_batch_results(
    entries: list[ManifestEntry],
    prior_results: list[ApiResult],
    execution: dict[str, object],
    run_dir: Path,
) -> list[ApiResult]:
    fresh = {result.canonical_name: result for result in create_results(entries, execution, run_dir, fix_mode="off")}
    merged: list[ApiResult] = []
    for result in prior_results:
        current = fresh[result.canonical_name]
        result.stage = "final"
        result.final_status = "fixed" if result.fix_applied and current.final_status == "pytest_passed" else current.final_status
        result.pytest_outcome = current.pytest_outcome
        result.failure_category = current.failure_category
        result.root_cause_summary = current.root_cause_summary
        result.failure_messages = current.failure_messages
        result.tests_total = current.tests_total
        result.passed_count = current.passed_count
        result.skipped_count = current.skipped_count
        result.xfailed_count = current.xfailed_count
        result.failed_count = current.failed_count
        result.error_count = current.error_count
        merged.append(result)
    return merged


def render_summary(
    results: list[ApiResult],
    run_dir: Path,
    input_path: Path,
    fix_mode: str,
    manifest_path: Path,
    final_command: str,
) -> str:
    total = len(results)
    counts: dict[str, int] = {}
    categories: dict[str, int] = {}
    fixed = [result for result in results if result.final_status == "fixed"]
    failed = [result for result in results if result.final_status in {"pytest_failed", "review_failed", "skip_heavy"}]
    skipped = [result for result in results if result.final_status == "skipped"]
    passed = [result for result in results if result.final_status in {"pytest_passed", "fixed"}]
    for result in results:
        counts[result.final_status] = counts.get(result.final_status, 0) + 1
        categories[result.failure_category] = categories.get(result.failure_category, 0) + 1

    lines = [
        f"# 流水线摘要：{run_dir.name}",
        "",
        f"- 输入：`{relative_to_root(input_path.resolve())}`",
        f"- 进度 CSV：`{relative_to_root(manifest_path)}`",
        f"- 修复模式：`{fix_mode}`",
        f"- 运行命令：`{final_command}`",
        f"- API 总数：`{total}`",
        f"- 结果 JSON：`{relative_to_root(run_dir / 'results.json')}`",
        f"- 结果 CSV：`{relative_to_root(run_dir / 'results.csv')}`",
        f"- 汇总表 CSV：`{relative_to_root(run_dir / 'summary_table.csv')}`",
        f"- **最终交付报告**：`{relative_to_root(run_dir / 'final_verdict.md')}`",
        f"- 最终交付 CSV：`{relative_to_root(run_dir / 'final_verdict.csv')}`",
        f"- 生成摘要：`{relative_to_root(run_dir / 'generation_summary.md')}`",
        f"- 分析摘要：`{relative_to_root(run_dir / 'analysis_summary.md')}`",
        "",
        "## 状态统计",
    ]
    for status in sorted(counts):
        lines.append(f"- `{status}`: {counts[status]}")
    lines.extend(["", "## 失败类别"])
    for category in sorted(categories):
        lines.append(f"- `{category}`: {categories[category]}")

    lines.extend(["", "## 已修复 API"])
    if fixed:
        for result in fixed:
            changed = ", ".join(result.changed_files) if result.changed_files else "未检测到文件变更"
            lines.append(
                f"- `{result.canonical_name}`: 初始分类 `{result.initial_failure_category}` -> "
                f"`{result.fix_target or '未知'}`；重跑结果 `{result.rerun_status}`；变更文件：{changed}"
            )
    else:
        lines.append("- 无")

    lines.extend(["", "## 仍有问题的 API"])
    if failed:
        for result in failed:
            lines.append(f"- `{result.canonical_name}`: `{result.failure_category}`；{result.root_cause_summary or '无摘要'}")
    else:
        lines.append("- 无")

    lines.extend(["", "## 跳过的 API"])
    if skipped:
        for result in skipped:
            lines.append(f"- `{result.canonical_name}`: `{result.final_status}`；{result.root_cause_summary or '无摘要'}")
    else:
        lines.append("- 无")

    lines.extend(["", "## 通过的 API"])
    if passed:
        lines.append(f"- 数量：{len(passed)}")
    else:
        lines.append("- 无")

    # --- 干预方式汇总（筛选指南）---
    human_results = [r for r in results if r.intervention_type == "human_required"]
    retry_results = [r for r in results if r.intervention_type == "agent_retry"]
    lines.extend(["", "## 需要人工介入"])
    lines.append(
        "> 在 `summary_table.csv` 中筛选 `Intervention Type == human_required` 即可获得此列表。"
    )
    if human_results:
        for result in human_results:
            lines.append(
                f"- `{result.canonical_name}`：原因=`{result.intervention_reason}` "
                f"类别=`{result.failure_category}`"
            )
    else:
        lines.append("- 无")

    lines.extend(["", "## 建议 AI 代理重试"])
    lines.append(
        "> 在 `summary_table.csv` 中筛选 `Intervention Type == agent_retry` 即可获得此列表。"
    )
    if retry_results:
        for result in retry_results:
            lines.append(
                f"- `{result.canonical_name}`：原因=`{result.intervention_reason}` "
                f"类别=`{result.failure_category}`"
            )
    else:
        lines.append("- 无")

    return "\n".join(lines) + "\n"


def _verdict_for_result(result: ApiResult) -> str:
    """Return a human-readable verdict label for a single API result."""
    if result.final_status in {"pytest_passed", "fixed"}:
        return "✅ AI 已确认"
    if result.intervention_type == "agent_retry":
        return "🔄 建议重试"
    if result.intervention_type == "human_required":
        return "🔧 需人工检查"
    return "❓ 未知"


def _verdict_sort_key(result: ApiResult) -> tuple[int, str]:
    """Sort results so that items needing attention appear first."""
    priority = {"🔧 需人工检查": 0, "🔄 建议重试": 1, "❓ 未知": 2, "✅ AI 已确认": 3}
    verdict = _verdict_for_result(result)
    return priority.get(verdict, 9), result.canonical_name


def render_final_verdict(results: list[ApiResult], run_dir: Path) -> str:
    """Render a user-facing final verdict report.

    This is the "single page" a user should read after a pipeline run.
    It answers two questions:
      1. Which APIs are done (AI confirmed, test file ready)?
      2. Which APIs still need human attention, and why?
    """
    sorted_results = sorted(results, key=_verdict_sort_key)

    confirmed = [r for r in results if _verdict_for_result(r) == "✅ AI 已确认"]
    needs_retry = [r for r in results if _verdict_for_result(r) == "🔄 建议重试"]
    needs_human = [r for r in results if _verdict_for_result(r) == "🔧 需人工检查"]

    total = len(results)
    lines: list[str] = []

    # Header
    lines.append(f"# 📋 最终交付报告：{run_dir.name}")
    lines.append("")
    lines.append(f"> 本报告是流水线运行后的**最终结论**。共 **{total}** 个 API，"
                 f"其中 **{len(confirmed)}** 个已确认通过、"
                 f"**{len(needs_retry)}** 个建议重试、"
                 f"**{len(needs_human)}** 个需人工检查。")
    lines.append("")

    # Progress bar
    pct = len(confirmed) * 100 // total if total else 0
    bar_filled = pct // 2
    bar_empty = 50 - bar_filled
    bar = "█" * bar_filled + "░" * bar_empty
    lines.append(f"**完成进度** `{bar}` **{pct}%** ({len(confirmed)}/{total})")
    lines.append("")

    # ---- Section 1: needs human attention ----
    lines.append("---")
    lines.append("")
    lines.append(f"## 🔧 需人工检查（{len(needs_human)} 个）")
    lines.append("")
    if needs_human:
        lines.append("| API | 测试文件 | 失败类别 | 原因 | 摘要 |")
        lines.append("|-----|----------|----------|------|------|")
        for r in needs_human:
            summary_text = (r.root_cause_summary or "—").split("\n")[0][:80]
            lines.append(
                f"| `{r.canonical_name}` "
                f"| `{r.file_name}` "
                f"| `{r.failure_category}` "
                f"| {r.intervention_reason} "
                f"| {summary_text} |"
            )
    else:
        lines.append("🎉 无！所有 API 均无需人工介入。")
    lines.append("")

    # ---- Section 2: retry candidates ----
    lines.append(f"## 🔄 建议 AI 重试（{len(needs_retry)} 个）")
    lines.append("")
    if needs_retry:
        lines.append("> 这些 API 的测试 Bug 可被 AI 修复，建议用 `--resume` 重跑或手动触发修复。")
        lines.append("")
        lines.append("| API | 测试文件 | 原因 | 摘要 |")
        lines.append("|-----|----------|------|------|")
        for r in needs_retry:
            summary_text = (r.root_cause_summary or "—").split("\n")[0][:80]
            lines.append(
                f"| `{r.canonical_name}` "
                f"| `{r.file_name}` "
                f"| {r.intervention_reason} "
                f"| {summary_text} |"
            )
    else:
        lines.append("无。")
    lines.append("")

    # ---- Section 3: confirmed ----
    lines.append(f"## ✅ AI 已确认通过（{len(confirmed)} 个）")
    lines.append("")
    if confirmed:
        lines.append("> 以下 API 的测试文件已生成且全部通过，可直接使用。")
        lines.append("")
        lines.append("<details>")
        lines.append(f"<summary>展开查看全部 {len(confirmed)} 个已通过的 API</summary>")
        lines.append("")
        lines.append("| API | 测试文件 | 测试数 | 通过 | 跳过 | 是否经修复 |")
        lines.append("|-----|----------|--------|------|------|------------|")
        for r in sorted(confirmed, key=lambda x: x.canonical_name):
            fixed_label = "✅ 是" if r.final_status == "fixed" else "—"
            lines.append(
                f"| `{r.canonical_name}` "
                f"| `{r.file_name}` "
                f"| {r.tests_total} "
                f"| {r.passed_count} "
                f"| {r.skipped_count} "
                f"| {fixed_label} |"
            )
        lines.append("")
        lines.append("</details>")
    else:
        lines.append("无。")
    lines.append("")

    # ---- Section 4: overall stats ----
    lines.append("---")
    lines.append("")
    lines.append("## 📊 统计总览")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| API 总数 | {total} |")
    lines.append(f"| ✅ AI 已确认 | {len(confirmed)} |")
    lines.append(f"| 🔄 建议重试 | {len(needs_retry)} |")
    lines.append(f"| 🔧 需人工检查 | {len(needs_human)} |")
    total_tests = sum(r.tests_total for r in results)
    total_passed = sum(r.passed_count for r in results)
    total_skipped = sum(r.skipped_count for r in results)
    total_failed = sum(r.failed_count for r in results) + sum(r.error_count for r in results)
    auto_fixed = [r for r in results if r.fix_applied]
    lines.append(f"| 测试用例总数 | {total_tests} |")
    lines.append(f"| 通过用例 | {total_passed} |")
    lines.append(f"| 跳过用例 | {total_skipped} |")
    lines.append(f"| 失败/错误用例 | {total_failed} |")
    lines.append(f"| AI 自动修复的 API | {len(auto_fixed)} |")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*  ")
    lines.append(f"*Run ID：`{run_dir.name}`*  ")
    lines.append(f"*详细过程日志见 `summary.md` · 结构化数据见 `final_verdict.csv`*")
    lines.append("")

    return "\n".join(lines)


def write_summary(
    results: list[ApiResult],
    run_dir: Path,
    input_path: Path,
    fix_mode: str,
    manifest_path: Path,
    command: str,
) -> None:
    summary = render_summary(results, run_dir, input_path, fix_mode, manifest_path, command)
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")

    # Generate the comprehensive CSV summary table (process-oriented)
    csv_path = run_dir / "summary_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "API Name", "Final Status", "Category", "Auto-Fix?", "Rerun Status",
            "Intervention Type", "Intervention Reason", "Quick Summary",
        ])
        for result in results:
            short_summary = result.root_cause_summary.replace('\n', ' ')
            fixed_val = "Yes" if result.fix_applied else "No"
            writer.writerow([
                result.canonical_name,
                result.final_status,
                result.failure_category,
                fixed_val,
                result.rerun_status,
                result.intervention_type,
                result.intervention_reason,
                short_summary,
            ])

    # Generate user-facing final verdict report and CSV
    verdict_md = render_final_verdict(results, run_dir)
    (run_dir / "final_verdict.md").write_text(verdict_md, encoding="utf-8")

    verdict_csv_path = run_dir / "final_verdict.csv"
    with verdict_csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "API", "测试文件", "结论", "测试数", "通过", "跳过",
            "失败类别", "是否经修复", "需要操作", "摘要",
        ])
        for result in sorted(results, key=_verdict_sort_key):
            verdict = _verdict_for_result(result)
            fixed_val = "是" if result.fix_applied else "否"
            action = {
                "✅ AI 已确认": "无需操作",
                "🔄 建议重试": "建议重跑",
                "🔧 需人工检查": "需人工处理",
                "❓ 未知": "待定",
            }.get(verdict, "待定")
            short_summary = (result.root_cause_summary or "").replace("\n", " ")[:120]
            writer.writerow([
                result.canonical_name,
                result.file_name,
                verdict,
                result.tests_total,
                result.passed_count,
                result.skipped_count,
                result.failure_category,
                fixed_val,
                action,
                short_summary,
            ])


def select_target_entries(entries: list[ManifestEntry]) -> list[ManifestEntry]:
    pending = [entry for entry in entries if entry.status == "pending"]
    return pending or entries


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PyTorch NPU API batch pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("build-manifest", help="Build api_manifest.csv from apis.txt")
    manifest_parser.add_argument("--input", required=True, type=Path, help="Path to apis.txt")
    manifest_parser.add_argument("--output", required=True, type=Path, help="Output CSV path")

    run_parser = subparsers.add_parser("run", help="Generate tests, run pytest, analyze results, and optionally fix simple issues")
    run_parser.add_argument("--input", required=True, type=Path, help="Path to apis.txt or api_manifest.csv")
    run_parser.add_argument("--report-dir", type=Path, default=RUNS_DIR, help="Base directory for run artifacts")
    run_parser.add_argument("--resume", type=Path, help="Reuse an existing run directory")
    run_parser.add_argument("--fix-mode", choices=sorted(FIX_MODES), default="tests", help="Automatic fix scope")
    run_parser.add_argument("--cli-backend", choices=sorted(SUPPORTED_BACKENDS), default="claude", help="Which AI CLI backend to use")
    run_parser.add_argument("--run-engine", choices=sorted(RUN_ENGINES), default="agent", help="How pytest is executed")
    run_parser.add_argument("--analysis-engine", choices=sorted(ANALYSIS_ENGINES), default="agent", help="How failure triage is performed")
    run_parser.add_argument("--skip-generate", action="store_true", help="Skip generation and reuse existing tests")
    run_parser.add_argument("--max-workers", type=int, default=8, help="Generation stage worker budget hint for nested agent")
    run_parser.add_argument("--debug", action="store_true", help="Enable debug mode to retain all intermediate subagent logs and full agent traces")
    return parser.parse_args(argv)


def do_build_manifest(args: argparse.Namespace) -> int:
    entries = build_manifest_from_text_input(args.input.resolve(), args.output.resolve())
    print(f"written: {args.output} ({len(entries)} rows)")
    return 0


def do_run(args: argparse.Namespace) -> int:
    start_time = time.time()
    backend = get_backend(args.cli_backend)
    run_dir = ensure_run_dir(args.report_dir, args.resume)
    logger = PipelineLogger(run_dir / "pipeline.log")
    
    if args.debug:
        logger.log(f"debug mode enabled: full {backend.name} and subagent traces will be collected")

    logger.log(
        "pipeline start "
        f"input={relative_to_root(args.input.resolve())} fix_mode={args.fix_mode} "
        f"cli_backend={backend.name} run_engine={args.run_engine} analysis_engine={args.analysis_engine} "
        f"run_dir={relative_to_root(run_dir)}"
    )
    entries, manifest_path = resolve_input_manifest(args.input, run_dir)
    target_entries = select_target_entries(entries)
    write_run_manifest(entries, manifest_path, selected_entries=target_entries, run_phase="queued")
    logger.log(
        "manifest ready "
        f"entries={len(entries)} target_entries={len(target_entries)} "
        f"manifest={relative_to_root(manifest_path)}"
    )

    if not args.skip_generate:
        context_dir = run_context_extraction_stage(manifest_path, run_dir, logger)
        run_generation_stage(manifest_path, run_dir, args.max_workers, backend, logger, context_dir=context_dir)
        write_run_manifest(entries, manifest_path, selected_entries=target_entries, run_phase="generated")
    else:
        (run_dir / "generation_summary.md").write_text(
            "生成阶段已跳过（--skip-generate 参数已设置）。\n",
            encoding="utf-8",
        )
        logger.log("stage=generation skip reason=skip_generate")
        write_run_manifest(entries, manifest_path, selected_entries=target_entries, run_phase="reused_existing")

    existing_entries = [entry for entry in target_entries if entry.test_path.exists()]
    missing_entries = [entry for entry in target_entries if not entry.test_path.exists()]
    logger.log(
        f"pytest targets ready existing_files={len(existing_entries)} missing_files={len(missing_entries)}"
    )
    execution = run_pytest_stage([entry.test_path for entry in existing_entries], run_dir, "initial", args.run_engine, backend, logger)
    results = create_results(target_entries, execution, run_dir, args.fix_mode)
    missing_names = {entry.canonical_name for entry in missing_entries}
    for result in results:
        if result.canonical_name in missing_names:
            result.stage = "review"
            result.final_status = "review_failed"
            result.pytest_outcome = "not_generated"
            result.failure_category = "TEST_BUG"
            result.root_cause_summary = "生成/审查阶段未创建预期的测试文件。"
            result.initial_failure_category = result.failure_category
            result.initial_root_cause_summary = result.root_cause_summary
            result.fix_recommendation, result.auto_fixable, result.fix_target = recommend_fix(result.failure_category, args.fix_mode)
    write_run_manifest(entries, manifest_path, selected_entries=target_entries, run_phase="initial_pytest", results=results)

    results = run_analysis_stage(results, run_dir, execution, args.fix_mode, args.analysis_engine, backend, logger)
    write_run_manifest(entries, manifest_path, selected_entries=target_entries, run_phase="analysis", results=results)
    results = apply_auto_fixes(results, run_dir, args.fix_mode, args.run_engine, backend, logger)
    write_run_manifest(entries, manifest_path, selected_entries=target_entries, run_phase="fix", results=results)

    # Iterative fix loop: after each fix+rerun, check for remaining TEST_BUG failures
    # and attempt to fix them again, up to MAX_FIX_ROUNDS total.
    MAX_FIX_ROUNDS = 3
    fix_round = 1
    while fix_round <= MAX_FIX_ROUNDS:
        rerun_files = [entry.test_path for entry in target_entries if entry.test_path.exists()]
        logger.log(f"stage=pytest rerun start round={fix_round} files={len(rerun_files)}")
        round_execution = run_pytest_stage(rerun_files, run_dir, f"postfix_batch_r{fix_round}", args.run_engine, backend, logger)
        results = merge_final_batch_results(target_entries, results, round_execution, run_dir)
        annotate_intervention_types(results)

        # Count remaining auto-fixable TEST_BUG failures
        remaining_test_bugs = [
            r for r in results
            if r.final_status in {"pytest_failed", "review_failed", "skip_heavy"}
            and r.failure_category in {"TEST_BUG", "SKIP_HEAVY"}
            and not r.fix_applied
        ]
        if not remaining_test_bugs:
            logger.log(f"stage=fix_loop done round={fix_round} reason=no_remaining_test_bugs")
            break

        logger.log(f"stage=fix_loop round={fix_round} remaining_test_bugs={len(remaining_test_bugs)}")

        # Re-run analysis on the remaining failures to get fresh failure messages
        results = run_analysis_stage(results, run_dir, round_execution, args.fix_mode, args.analysis_engine, backend, logger)
        # Mark remaining test bugs as fixable and attempt fixes
        for r in results:
            if r.final_status in {"pytest_failed", "review_failed", "skip_heavy"} \
                    and r.failure_category in {"TEST_BUG", "SKIP_HEAVY"} \
                    and not r.fix_applied:
                r.auto_fixable = True
                r.fix_recommendation = "adjust_test"
                r.fix_target = "test/api_test"
        results = apply_auto_fixes(results, run_dir, args.fix_mode, args.run_engine, backend, logger)
        write_run_manifest(entries, manifest_path, selected_entries=target_entries, run_phase=f"fix_r{fix_round}", results=results)

        if not any(r.fix_applied for r in remaining_test_bugs):
            logger.log(f"stage=fix_loop done round={fix_round} reason=no_fix_applied")
            break
        fix_round += 1

    # If we exited the loop without a final merge, do one last rerun
    if fix_round > MAX_FIX_ROUNDS:
        logger.log(f"stage=fix_loop done round={MAX_FIX_ROUNDS} reason=max_rounds_reached")

    annotate_intervention_types(results)
    write_run_manifest(entries, manifest_path, selected_entries=target_entries, run_phase="final", results=results)

    write_results(results, run_dir)
    command_parts = [sys.executable, "-m", "scripts.pipeline", "run", "--input", str(args.input), "--fix-mode", args.fix_mode]
    if args.cli_backend != "claude":
        command_parts.extend(["--cli-backend", args.cli_backend])
    if args.run_engine != "agent":
        command_parts.extend(["--run-engine", args.run_engine])
    if args.analysis_engine != "agent":
        command_parts.extend(["--analysis-engine", args.analysis_engine])
    if args.skip_generate:
        command_parts.append("--skip-generate")
    if args.resume:
        command_parts.extend(["--resume", str(args.resume)])
    if args.report_dir:
        command_parts.extend(["--report-dir", str(args.report_dir)])
    if args.max_workers != 8:
        command_parts.extend(["--max-workers", str(args.max_workers)])
    if args.debug:
        command_parts.append("--debug")
    command_text = " ".join(shlex.quote(part) for part in command_parts)
    write_summary(results, run_dir, args.input, args.fix_mode, manifest_path, command_text)

    # Always collect agent session logs for traceability
    collect_session_logs(backend, start_time, run_dir / "agent_logs", logger)

    logger.log(
        "pipeline done "
        f"results_json={relative_to_root(run_dir / 'results.json')} "
        f"results_csv={relative_to_root(run_dir / 'results.csv')} "
        f"summary={relative_to_root(run_dir / 'summary.md')} "
        f"final_verdict={relative_to_root(run_dir / 'final_verdict.md')}"
    )
    print(relative_to_root(run_dir / "final_verdict.md"))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.command == "build-manifest":
        return do_build_manifest(args)
    if args.command == "run":
        return do_run(args)
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
