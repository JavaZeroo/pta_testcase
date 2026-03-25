"""Build unified API context files for the test generation pipeline.

Combines output from ``extract_api_doc`` and ``extract_api_tests`` into a
single JSON per API, ready to be injected into subagent prompts.

Usage:
    # From manifest CSV (only pending APIs):
    python -m scripts.build_api_context --manifest api_manifest.csv --output-dir api_context/

    # From API list file:
    python -m scripts.build_api_context --api-list apis.txt --output-dir api_context/

    # Single API:
    python -m scripts.build_api_context --api "torch.nn.Linear" --output-dir api_context/

    # Incremental (skip existing):
    python -m scripts.build_api_context --manifest api_manifest.csv --output-dir api_context/ --incremental
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.extract_api_doc import extract_api_doc
from scripts.extract_api_tests import extract_api_tests

ROOT = Path(__file__).resolve().parent.parent


def _safe_filename(api_name: str) -> str:
    """Convert an API name to a safe filename component."""
    return api_name.replace(".", "_")


def build_context_for_api(api_name: str, file_name: str = "") -> dict:
    """Build a full context dict for one API."""
    doc = extract_api_doc(api_name)
    tests = extract_api_tests(api_name)

    return {
        "api_name": api_name,
        "file_name": file_name,
        "doc": doc.to_dict(),
        "test_references": tests.to_dict(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_apis_from_manifest(manifest_path: Path, only_pending: bool = True) -> list[tuple[str, str]]:
    """Load (canonical_name, file_name) pairs from a CSV manifest."""
    pairs: list[tuple[str, str]] = []
    with manifest_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("canonical_name") or "").strip()
            fname = (row.get("file_name") or "").strip()
            status = (row.get("status") or "").strip()
            if not name:
                continue
            if only_pending and status not in ("pending", ""):
                continue
            pairs.append((name, fname))
    return pairs


def _load_apis_from_list(list_path: Path) -> list[tuple[str, str]]:
    """Load API names from a text file (one per line)."""
    pairs: list[tuple[str, str]] = []
    for line in list_path.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if name and not name.startswith("#"):
            pairs.append((name, ""))
    return pairs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build API context files")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path, help="CSV manifest file")
    source.add_argument("--api-list", type=Path, help="Text file with one API per line")
    source.add_argument("--api", type=str, help="Single API name")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "api_context",
                        help="Output directory (default: api_context/)")
    parser.add_argument("--incremental", action="store_true",
                        help="Skip APIs that already have a context file")
    parser.add_argument("--all-status", action="store_true",
                        help="Process all APIs regardless of status (manifest mode)")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    # Collect API list
    apis: list[tuple[str, str]] = []
    if args.api:
        apis = [(args.api, "")]
    elif args.api_list:
        apis = _load_apis_from_list(args.api_list)
    elif args.manifest:
        apis = _load_apis_from_manifest(args.manifest, only_pending=not args.all_status)

    if not apis:
        print("No APIs to process.", file=sys.stderr)
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)

    skipped = 0
    written = 0
    for i, (api_name, file_name) in enumerate(apis):
        safe = _safe_filename(api_name)
        out_path = args.output_dir / f"{safe}.json"

        if args.incremental and out_path.exists():
            skipped += 1
            continue

        print(f"  [{i+1}/{len(apis)}] {api_name} ...", end="", flush=True, file=sys.stderr)
        ctx = build_context_for_api(api_name, file_name)
        out_path.write_text(
            json.dumps(ctx, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        doc_src = ctx["doc"]["source"]
        n_tests = len(ctx["test_references"]["test_references"])
        print(f" doc={doc_src}, tests={n_tests}", file=sys.stderr)
        written += 1

    print(
        f"\nDone: {written} written, {skipped} skipped (incremental), "
        f"{len(apis)} total APIs",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
