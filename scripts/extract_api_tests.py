"""Extract PyTorch upstream test references for a given API.

Searches ``pytorch/test/`` for usages of the target API name, locates the
enclosing test function/method, and returns structured snippets.

Usage:
    python -m scripts.extract_api_tests "torch.nn.Linear"
    python -m scripts.extract_api_tests --api-list apis.txt --output-dir api_context/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
PYTORCH_TEST_DIR = ROOT / "pytorch" / "test"

# Limits
MAX_SNIPPETS_PER_API = 5
MAX_SNIPPET_LINES = 80


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TestSnippet:
    file: str
    line_start: int
    line_end: int
    function_name: str
    snippet: str


@dataclass
class ApiTestReferences:
    api_name: str
    test_references: list[TestSnippet] = field(default_factory=list)
    total_matches: int = 0
    files_with_matches: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Search pattern generation
# ---------------------------------------------------------------------------

def _build_search_patterns(api_name: str) -> list[str]:
    """Generate search patterns for ripgrep/grep from an API name.

    Returns patterns in decreasing specificity order.
    """
    patterns: list[str] = []

    # Remove leading "torch." for short form
    short = api_name
    if short.startswith("torch."):
        short = short[len("torch."):]

    # Full qualified name with call or assignment: torch.nn.Linear(
    patterns.append(re.escape(api_name))

    # Short form: nn.Linear(  (only if it's not just a single token)
    if "." in short:
        patterns.append(re.escape(short))

    # For Tensor methods: .method_name(
    if api_name.startswith("Tensor.") or api_name.startswith("torch.Tensor."):
        method = api_name.split(".")[-1]
        patterns.append(rf"\.{re.escape(method)}\s*\(")

    # For nn.Module methods: .method_name(
    if "Module." in api_name:
        method = api_name.split(".")[-1]
        patterns.append(rf"\.{re.escape(method)}\s*\(")

    # For nn.Parameter attributes (inherits from Tensor): search for
    # Parameter usage patterns like param.grad, param.device, etc.
    if "Parameter." in api_name:
        attr = api_name.split(".")[-1]
        # Match both .attr access and .attr( call
        patterns.append(rf"\.{re.escape(attr)}[\s\(\)\.]")
        # Also search for parameter-specific test patterns
        patterns.append(rf"Parameter\(.*\)\.{re.escape(attr)}")

    return patterns


# ---------------------------------------------------------------------------
# File searching (uses ripgrep if available, falls back to grep)
# ---------------------------------------------------------------------------

def _find_matches(pattern: str, search_dir: Path) -> list[tuple[str, int]]:
    """Search for *pattern* in Python test files under *search_dir*.

    Returns list of (relative_file_path, line_number) tuples.
    """
    matches: list[tuple[str, int]] = []

    # Try ripgrep first
    try:
        result = subprocess.run(
            ["rg", "-n", "--no-heading", "--glob", "*.py", pattern, str(search_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in result.stdout.splitlines():
            # Format: filepath:lineno:content
            parts = line.split(":", 2)
            if len(parts) >= 2:
                filepath = parts[0]
                try:
                    lineno = int(parts[1])
                    rel_path = os.path.relpath(filepath, ROOT)
                    matches.append((rel_path, lineno))
                except ValueError:
                    continue
        return matches
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback to Python grep
    for py_file in search_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, file_line in enumerate(content.splitlines(), 1):
            if re.search(pattern, file_line):
                rel_path = str(py_file.relative_to(ROOT))
                matches.append((rel_path, i))

    return matches


# ---------------------------------------------------------------------------
# Function boundary detection
# ---------------------------------------------------------------------------

def _extract_enclosing_function(filepath: Path, target_line: int) -> Optional[tuple[str, int, int, str]]:
    """Find the enclosing test function/method for a given line.

    Returns (function_name, start_line, end_line, snippet) or None.
    """
    try:
        lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None

    if target_line < 1 or target_line > len(lines):
        return None

    # Walk backward to find the `def` line
    func_start = None
    func_name = ""
    indent_level = None
    for i in range(target_line - 1, -1, -1):
        line = lines[i]
        m = re.match(r"^(\s*)(def|async\s+def)\s+(\w+)\s*\(", line)
        if m:
            indent_level = len(m.group(1))
            func_name = m.group(3)
            func_start = i + 1  # 1-indexed
            break

    if func_start is None:
        return None

    # Walk forward to find the end of the function
    func_end = len(lines)
    for i in range(func_start, len(lines)):
        line = lines[i]
        # End of function: next line at same or lesser indent that's not blank/comment
        if i > func_start - 1:
            stripped = line.rstrip()
            if stripped and not stripped.lstrip().startswith("#"):
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= indent_level and not line[indent_level:].startswith(" "):
                    # Check it's a new def/class or top-level statement
                    if re.match(r"^(\s*)(def|async\s+def|class)\s+", line) or current_indent < indent_level:
                        func_end = i  # 0-indexed, exclusive
                        break

    func_end_1indexed = min(func_end, len(lines))

    # Truncate if too long
    snippet_start = func_start - 1  # 0-indexed
    snippet_end = min(snippet_start + MAX_SNIPPET_LINES, func_end_1indexed)
    snippet_lines = lines[snippet_start:snippet_end]
    if snippet_end < func_end_1indexed:
        snippet_lines.append(f"    # ... (truncated, {func_end_1indexed - snippet_start} total lines)")

    snippet = "\n".join(snippet_lines)
    return func_name, func_start, func_end_1indexed, snippet


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def _score_snippet(api_name: str, file_path: str, func_name: str, snippet: str) -> float:
    """Score a test snippet for relevance to the API."""
    score = 0.0
    api_short = api_name.split(".")[-1].lower()

    # Function name contains API name part
    if api_short in func_name.lower():
        score += 10.0

    # File name contains API name part
    basename = os.path.basename(file_path).lower()
    if api_short in basename:
        score += 5.0

    # Count occurrences of API in snippet
    count = snippet.lower().count(api_name.lower())
    short = api_name.replace("torch.", "")
    count += snippet.lower().count(short.lower())
    score += min(count, 5) * 2.0

    # Prefer test functions (not helpers)
    if func_name.startswith("test_"):
        score += 3.0

    # Shorter snippets slightly preferred (more focused)
    line_count = snippet.count("\n") + 1
    if line_count < 30:
        score += 1.0

    return score


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_api_tests(api_name: str) -> ApiTestReferences:
    """Extract test references for a single API."""
    if not PYTORCH_TEST_DIR.exists():
        return ApiTestReferences(api_name=api_name)

    patterns = _build_search_patterns(api_name)

    # Collect all matches across patterns, dedup by (file, line)
    all_matches: dict[tuple[str, int], None] = {}
    for pattern in patterns:
        matches = _find_matches(pattern, PYTORCH_TEST_DIR)
        for m in matches:
            all_matches[m] = None

    total_matches = len(all_matches)
    files_with_matches = len({f for f, _ in all_matches})

    # Group by file, then extract enclosing functions
    seen_functions: set[tuple[str, str]] = set()  # (file, func_name)
    candidates: list[tuple[float, TestSnippet]] = []

    for (rel_path, lineno) in all_matches:
        abs_path = ROOT / rel_path
        result = _extract_enclosing_function(abs_path, lineno)
        if result is None:
            continue

        func_name, start, end, snippet = result
        key = (rel_path, func_name)
        if key in seen_functions:
            continue
        seen_functions.add(key)

        score = _score_snippet(api_name, rel_path, func_name, snippet)
        candidates.append((
            score,
            TestSnippet(
                file=rel_path,
                line_start=start,
                line_end=end,
                function_name=func_name,
                snippet=snippet,
            ),
        ))

    # Sort by relevance, take top N
    candidates.sort(key=lambda x: x[0], reverse=True)
    top_snippets = [s for _, s in candidates[:MAX_SNIPPETS_PER_API]]

    return ApiTestReferences(
        api_name=api_name,
        test_references=top_snippets,
        total_matches=total_matches,
        files_with_matches=files_with_matches,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract PyTorch test references for APIs")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("api_name", nargs="?", help="Single API name")
    group.add_argument("--api-list", type=Path, help="File with one API per line")
    parser.add_argument("--output-dir", type=Path, help="Write JSON files to this directory")
    parser.add_argument("--pretty", action="store_true", default=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    api_names: list[str] = []
    if args.api_name:
        api_names = [args.api_name]
    elif args.api_list:
        api_names = [
            line.strip()
            for line in args.api_list.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    results: list[dict] = []
    for i, api_name in enumerate(api_names):
        refs = extract_api_tests(api_name)
        results.append(refs.to_dict())
        print(
            f"  [{i+1}/{len(api_names)}] {api_name}: "
            f"{len(refs.test_references)} snippets from {refs.files_with_matches} files "
            f"({refs.total_matches} total matches)",
            file=sys.stderr,
        )

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for result in results:
            safe_name = result["api_name"].replace(".", "_")
            out_path = args.output_dir / f"{safe_name}.tests.json"
            out_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None),
                encoding="utf-8",
            )
        print(f"Wrote {len(results)} test reference files to {args.output_dir}", file=sys.stderr)
    else:
        indent = 2 if args.pretty else None
        if len(results) == 1:
            print(json.dumps(results[0], ensure_ascii=False, indent=indent))
        else:
            print(json.dumps(results, ensure_ascii=False, indent=indent))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
