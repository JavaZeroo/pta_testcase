"""Extract structured API documentation from local PyTorch HTML docs.

Usage:
    python -m scripts.extract_api_doc "torch.nn.Linear"
    python -m scripts.extract_api_doc "torch.abs" --output-dir api_context/
    python -m scripts.extract_api_doc --api-list apis.txt --output-dir api_context/

Strategies (in priority order):
1. Direct HTML file: pytorch/docs/build/html/generated/{api}.html
2. Search index lookup: searchindex.js → locate parent page + anchor
3. Python introspection: pydoc fallback for undocumented / private APIs
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import textwrap
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent.parent
DOCS_HTML = ROOT / "pytorch" / "docs" / "build" / "html"
GENERATED_DIR = DOCS_HTML / "generated"
SEARCH_INDEX_PATH = DOCS_HTML / "searchindex.js"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ParamInfo:
    name: str
    type: str = ""
    description: str = ""


@dataclass
class ApiDoc:
    api_name: str
    source: str = "not_found"  # "html" | "introspection" | "not_found"
    signature: str = ""
    description: str = ""
    parameters: list[ParamInfo] = field(default_factory=list)
    return_info: str = ""
    examples: list[str] = field(default_factory=list)
    notes: str = ""
    doc_page: str = ""
    source_code: str = ""  # API 完整源码，用于分支覆盖分析

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Search index loader (cached)
# ---------------------------------------------------------------------------

_search_index_cache: dict | None = None


def _load_search_index() -> dict:
    """Parse ``searchindex.js`` and return the decoded dict."""
    global _search_index_cache
    if _search_index_cache is not None:
        return _search_index_cache

    text = SEARCH_INDEX_PATH.read_text(encoding="utf-8")
    text = text.replace("Search.setIndex(", "", 1)
    if text.endswith(")"):
        text = text[:-1]
    _search_index_cache = json.loads(text)
    return _search_index_cache


def _resolve_doc_page(api_name: str) -> Optional[str]:
    """Use the search index to find which doc page contains *api_name*.

    Returns a path relative to the HTML root (e.g. ``generated/torch.nn.Module``)
    or *None*.
    """
    idx = _load_search_index()
    docnames: list[str] = idx["docnames"]
    objects: dict = idx["objects"]

    # Split into namespace + method
    parts = api_name.rsplit(".", 1)
    if len(parts) == 2:
        namespace, method = parts
    else:
        namespace, method = "", parts[0]

    # Try exact namespace match first
    if namespace in objects:
        for item in objects[namespace]:
            doc_idx, _type_idx, _prio, _deprecated, name = item
            if name == method:
                return docnames[doc_idx]

    # Try parent namespaces (e.g. torch.nn.Module.named_modules → torch.nn.Module)
    # Walk up the namespace
    ns = api_name
    while "." in ns:
        ns = ns.rsplit(".", 1)[0]
        if ns in objects:
            remaining = api_name[len(ns) + 1:]
            for item in objects[ns]:
                doc_idx, _type_idx, _prio, _deprecated, name = item
                if name == remaining or name == remaining.split(".")[-1]:
                    return docnames[doc_idx]

    return None


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Collapse whitespace, strip leading/trailing."""
    return re.sub(r"\s+", " ", text).strip()


def _extract_signature_from_dt(dt: Tag) -> str:
    """Extract the function/class signature from a ``<dt>`` element.

    Reconstructs the signature by walking the DOM tree of the ``<dt>``
    and preserving text nodes and ``<span class="pre">`` content so that
    type annotations are kept intact.
    """
    import copy
    dt = copy.copy(dt)
    # Remove ¶ permalink and [source] anchors
    for a in dt.find_all("a", class_="headerlink"):
        a.decompose()
    for span in dt.find_all("span", class_="viewcode-link"):
        span.decompose()

    # Strategy: collect .pre span texts + inter-element text nodes
    # This preserves type annotations that live inside nested spans
    raw = dt.get_text(separator="", strip=False)
    # Clean up common artifacts
    raw = raw.replace("\u00b6", "")  # remove ¶
    raw = raw.replace("[source]", "")
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _extract_params_from_dd(dd: Tag) -> list[ParamInfo]:
    """Parse parameter info from field-list inside a ``<dd>`` block."""
    params: list[ParamInfo] = []
    field_lists = dd.find_all("dl", class_="field-list")
    for fl in field_lists:
        dts = fl.find_all("dt", recursive=False)
        dds = fl.find_all("dd", recursive=False)
        for dt_f, dd_f in zip(dts, dds):
            field_name = _clean_text(dt_f.get_text()).lower()
            if "parameter" not in field_name and "argument" not in field_name:
                continue
            # Each param may be a <li> or a <p>
            lis = dd_f.find_all("li")
            items = lis if lis else dd_f.find_all("p")
            for item in items:
                raw = _clean_text(item.get_text())
                param = _parse_param_text(raw)
                if param:
                    params.append(param)
    return params


def _parse_param_text(text: str) -> Optional[ParamInfo]:
    """Parse a single parameter text like ``name (type) – description``."""
    # Pattern: name (type) – description  OR  name – description
    m = re.match(r"^(\w+)\s*\(([^)]*)\)\s*[–\-]\s*(.*)", text)
    if m:
        return ParamInfo(name=m.group(1), type=m.group(2).strip(), description=m.group(3).strip())
    m = re.match(r"^(\w+)\s*[–\-]\s*(.*)", text)
    if m:
        return ParamInfo(name=m.group(1), description=m.group(2).strip())
    return None


def _extract_returns_from_dd(dd: Tag) -> str:
    """Extract return info from field-list."""
    field_lists = dd.find_all("dl", class_="field-list")
    for fl in field_lists:
        dts = fl.find_all("dt", recursive=False)
        dds = fl.find_all("dd", recursive=False)
        for dt_f, dd_f in zip(dts, dds):
            field_name = _clean_text(dt_f.get_text()).lower()
            if "return" in field_name:
                return _clean_text(dd_f.get_text())
    return ""


def _extract_examples_from_dd(dd: Tag) -> list[str]:
    """Extract example code blocks (deduplicated)."""
    examples: list[str] = []
    seen: set[str] = set()
    for block in dd.find_all("div", class_=re.compile(r"highlight|doctest")):
        code = block.get_text().strip()
        if code and ">>>" in code and code not in seen:
            seen.add(code)
            examples.append(code)
    return examples


def _extract_description_from_dd(dd: Tag) -> str:
    """Extract the main description paragraphs (before field-lists)."""
    parts: list[str] = []
    for child in dd.children:
        if isinstance(child, Tag):
            if child.name == "dl" and "field-list" in (child.get("class") or []):
                break
            if child.name == "p":
                text = _clean_text(child.get_text())
                if text:
                    parts.append(text)
        elif isinstance(child, str):
            text = child.strip()
            if text:
                parts.append(text)
    return " ".join(parts)


def _extract_notes_from_dd(dd: Tag) -> str:
    """Extract notes/warnings from admonition blocks."""
    notes: list[str] = []
    for adm in dd.find_all("div", class_=re.compile(r"admonition|note|warning")):
        text = _clean_text(adm.get_text())
        if text:
            notes.append(text)
    return " ".join(notes)[:500] if notes else ""


# ---------------------------------------------------------------------------
# Strategy 1: Direct HTML file
# ---------------------------------------------------------------------------

def _try_direct_html(api_name: str) -> Optional[ApiDoc]:
    """Try to load from ``generated/{api_name}.html``."""
    html_file = GENERATED_DIR / f"{api_name}.html"
    if not html_file.exists():
        return None
    return _parse_html_page(api_name, html_file, api_name)


# ---------------------------------------------------------------------------
# Strategy 2: Search index → parent page + anchor
# ---------------------------------------------------------------------------

def _try_search_index(api_name: str) -> Optional[ApiDoc]:
    """Use searchindex.js to locate the API's documentation page and anchor."""
    doc_page = _resolve_doc_page(api_name)
    if doc_page is None:
        return None

    # Resolve the HTML file
    html_file = DOCS_HTML / f"{doc_page}.html"
    if not html_file.exists():
        return None

    return _parse_html_page(api_name, html_file, api_name)


def _parse_html_page(api_name: str, html_file: Path, anchor_id: str) -> Optional[ApiDoc]:
    """Parse an HTML page looking for a ``<dt id="{anchor_id}">`` element."""
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    # Find the dt with matching id
    dt = soup.find("dt", id=anchor_id)
    if dt is None:
        # Fallback: find the first main definition
        article = soup.find("article") or soup
        dl = article.find("dl", class_="py")
        if dl:
            dt = dl.find("dt")
    if dt is None:
        return None

    signature = _extract_signature_from_dt(dt)
    dd = dt.find_next_sibling("dd")
    if dd is None:
        return ApiDoc(
            api_name=api_name,
            source="html",
            signature=signature,
            doc_page=str(html_file.relative_to(DOCS_HTML)),
        )

    return_info = _extract_returns_from_dd(dd)
    # Fallback: extract return type from signature if not in field-list
    if not return_info and "→" in signature:
        return_info = signature.split("→", 1)[1].strip()

    return ApiDoc(
        api_name=api_name,
        source="html",
        signature=signature,
        description=_extract_description_from_dd(dd),
        parameters=_extract_params_from_dd(dd),
        return_info=return_info,
        examples=_extract_examples_from_dd(dd),
        notes=_extract_notes_from_dd(dd),
        doc_page=str(html_file.relative_to(DOCS_HTML)),
    )


# ---------------------------------------------------------------------------
# Strategy 3: Python introspection
# ---------------------------------------------------------------------------

def _try_introspection(api_name: str) -> Optional[ApiDoc]:
    """Fallback: use importlib + pydoc + source inspection to extract docs."""
    try:
        obj = _resolve_object(api_name)
    except Exception:
        return None

    if obj is None:
        return None

    import inspect
    import pydoc

    is_callable = callable(obj)
    is_simple_value = isinstance(obj, (bool, int, float, str, type(None)))

    # For simple values (config flags, constants), report what they are
    if is_simple_value:
        return ApiDoc(
            api_name=api_name,
            source="introspection",
            signature=f"{api_name} = {obj!r}",
            description=f"Configuration value / constant. Current value: {obj!r} (type: {type(obj).__name__})",
        )

    # Get signature via inspect
    sig_str = ""
    try:
        sig = inspect.signature(obj)
        sig_str = f"{api_name}{sig}"
    except (ValueError, TypeError):
        pass

    # Get the object's own docstring
    raw_doc = ""
    if is_callable or inspect.isclass(obj) or inspect.ismodule(obj):
        raw_doc = getattr(obj, "__doc__", "") or ""
    else:
        obj_doc = getattr(obj, "__doc__", "") or ""
        type_doc = getattr(type(obj), "__doc__", "") or ""
        if obj_doc and obj_doc != type_doc:
            raw_doc = obj_doc

    # Get pydoc text (richer for C++/pybind11 types)
    pydoc_text = ""
    if is_callable or inspect.isclass(obj) or inspect.ismodule(obj):
        try:
            pydoc_text = pydoc.render_doc(obj, title="%s")
            lines = pydoc_text.split("\n")
            pydoc_text = "\n".join(lines[1:]).strip()
            # pydoc uses overstriking (char\bchar) for bold — strip it
            pydoc_text = re.sub(r".\x08", "", pydoc_text)
        except Exception:
            pydoc_text = ""

    # Try to get source code — 完整保留，不截断，以确保所有分支可见
    source_snippet = ""
    try:
        source_snippet = inspect.getsource(obj)
    except (OSError, TypeError):
        pass

    if not sig_str and not raw_doc and not pydoc_text and not source_snippet:
        return ApiDoc(
            api_name=api_name,
            source="introspection",
            description=f"Object of type {type(obj).__name__}. No documentation available.",
        )

    # Try to extract signature from docstring if inspect failed
    if not sig_str:
        for source_text in [raw_doc, pydoc_text]:
            if not source_text:
                continue
            for line in source_text.split("\n"):
                line = line.strip()
                if "(" in line and ")" in line and api_name.split(".")[-1] in line:
                    sig_str = line.split("\n")[0]
                    break
            if sig_str:
                break

    # Extract description (first meaningful paragraph of docstring)
    description = ""
    if raw_doc:
        paragraphs = raw_doc.strip().split("\n\n")
        for para in paragraphs:
            text = para.strip()
            if text and "(" not in text.split("\n")[0]:
                description = _clean_text(text)
                break
            elif text and len(paragraphs) > 1:
                continue

    # For pybind11/C++ types with no raw_doc description, use pydoc summary
    if not description and pydoc_text:
        for line in pydoc_text.split("\n"):
            line = line.strip()
            if line and not line.startswith("|") and not line.startswith("class ") and "Method resolution" not in line:
                description = _clean_text(line)
                break

    # Extract examples from docstring
    examples: list[str] = []
    for doc_source in [raw_doc, pydoc_text]:
        if not doc_source or ">>>" not in doc_source:
            continue
        in_example = False
        example_lines: list[str] = []
        for line in doc_source.split("\n"):
            stripped = line.strip()
            if stripped.startswith(">>>") or stripped.startswith("..."):
                in_example = True
                example_lines.append(stripped)
            elif in_example:
                if stripped and not stripped.startswith(">>>"):
                    example_lines.append(stripped)
                else:
                    if example_lines:
                        examples.append("\n".join(example_lines))
                        example_lines = []
                    if stripped.startswith(">>>"):
                        example_lines.append(stripped)
                    else:
                        in_example = False
        if example_lines:
            examples.append("\n".join(example_lines))
        if examples:
            break  # Use first source that provides examples

    # Build notes from pydoc for C++ types (method listing etc.)
    notes = ""
    if pydoc_text and not raw_doc:
        # Extract method summaries for classes
        method_lines: list[str] = []
        in_methods = False
        for line in pydoc_text.split("\n"):
            if "Methods defined here" in line or "Data descriptors" in line:
                in_methods = True
                continue
            if in_methods:
                stripped = line.strip()
                if stripped.startswith("|") and "=" not in stripped:
                    clean = stripped.lstrip("| ").strip()
                    if clean and not clean.startswith("--"):
                        method_lines.append(clean)
                elif stripped and not stripped.startswith("|"):
                    in_methods = False
        if method_lines:
            notes = "Available methods/attributes: " + "; ".join(method_lines[:20])

    # notes 保留 pydoc 摘要；source_code 独立存放完整源码
    final_notes = notes[:500] if notes else ""

    return ApiDoc(
        api_name=api_name,
        source="introspection",
        signature=sig_str,
        description=description,
        parameters=_extract_params_from_docstring(raw_doc) if raw_doc else [],
        examples=examples,
        notes=final_notes if final_notes else "",
        source_code=source_snippet,
    )


def _extract_params_from_docstring(doc: str) -> list[ParamInfo]:
    """Extract parameter info from a raw docstring (Args/Parameters section)."""
    params: list[ParamInfo] = []
    in_params = False
    current_indent: int | None = None
    for line in doc.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith(("args:", "parameters:", "keyword args:", "keyword arguments:")):
            in_params = True
            continue
        if in_params:
            if not stripped:
                continue
            # Detect end of params section
            if stripped.lower().startswith(("returns:", "return:", "yields:", "raises:", "example", "note:")):
                break
            # Try to parse parameter line
            param = _parse_param_text(stripped)
            if param:
                params.append(param)
    return params


def _resolve_object(api_name: str):
    """Resolve a dotted API name to a Python object."""
    parts = api_name.split(".")
    # Try importing progressively longer module paths
    obj = None
    for i in range(len(parts), 0, -1):
        module_path = ".".join(parts[:i])
        try:
            obj = importlib.import_module(module_path)
            # Now traverse remaining attributes
            for attr_name in parts[i:]:
                obj = getattr(obj, attr_name)
            return obj
        except (ImportError, AttributeError, ModuleNotFoundError):
            continue
    return None


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def _try_get_source_code(api_name: str) -> str:
    """尝试通过 inspect.getsource 获取 API 的完整源码。"""
    import inspect
    try:
        obj = _resolve_object(api_name)
        if obj is not None:
            return inspect.getsource(obj)
    except (OSError, TypeError, Exception):
        pass
    return ""


def extract_api_doc(api_name: str) -> ApiDoc:
    """Extract documentation for a single API using the priority chain."""
    # Normalize: handle Tensor.xxx → torch.Tensor.xxx
    normalized = api_name
    if api_name.startswith("Tensor."):
        normalized = f"torch.{api_name}"

    # Strategy 1: Direct HTML
    result = _try_direct_html(normalized)
    if result is not None:
        result.api_name = api_name
        # HTML 策略也补充完整源码，确保分支覆盖分析可用
        if not result.source_code:
            result.source_code = _try_get_source_code(normalized)
        return result

    # Strategy 2: Search index
    result = _try_search_index(normalized)
    if result is not None:
        result.api_name = api_name
        if not result.source_code:
            result.source_code = _try_get_source_code(normalized)
        return result

    # Strategy 3: Python introspection
    result = _try_introspection(normalized)
    if result is not None:
        result.api_name = api_name
        return result

    return ApiDoc(api_name=api_name, source="not_found")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract PyTorch API documentation")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("api_name", nargs="?", help="Single API name, e.g. torch.nn.Linear")
    group.add_argument("--api-list", type=Path, help="File with one API per line (e.g. apis.txt)")
    parser.add_argument("--output-dir", type=Path, help="Write JSON files to this directory")
    parser.add_argument("--pretty", action="store_true", default=True, help="Pretty-print JSON")
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
    for api_name in api_names:
        doc = extract_api_doc(api_name)
        results.append(doc.to_dict())

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for result in results:
            # Use canonical name as filename
            safe_name = result["api_name"].replace(".", "_")
            out_path = args.output_dir / f"{safe_name}.doc.json"
            out_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None),
                encoding="utf-8",
            )
        print(f"Wrote {len(results)} doc files to {args.output_dir}")
    else:
        indent = 2 if args.pretty else None
        if len(results) == 1:
            print(json.dumps(results[0], ensure_ascii=False, indent=indent))
        else:
            print(json.dumps(results, ensure_ascii=False, indent=indent))

    # Summary
    sources = {}
    for r in results:
        s = r["source"]
        sources[s] = sources.get(s, 0) + 1
    print(f"Summary: {sources}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
