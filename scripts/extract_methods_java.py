#!/usr/bin/env python3
"""
Extract Java methods (and constructors) from a directory tree using Tree-sitter.

✅ Works WITHOUT building a custom .so/.dylib if you have `tree_sitter_java` installed
   (you do: modules/ast-extractor/.venv/.../tree_sitter_java/_binding.abi3.so)

Usage:
  python3 scripts/extract_methods_java.py \
    --root /path/to/commons-io \
    --out /tmp/commons_io_methods.json

If your `python3` is NOT the same venv where tree_sitter_java is installed, use:
  modules/ast-extractor/.venv/bin/python scripts/extract_methods_java.py --root ... --out ...
"""

import argparse
import json
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from tree_sitter import Parser, Language


# ----------------------------
# Data model
# ----------------------------
@dataclass
class ExtractedMethod:
    file: str
    class_name: Optional[str]
    method_name: str
    kind: str  # "method" | "constructor"
    start_line: int  # 1-based
    end_line: int    # 1-based
    start_byte: int
    end_byte: int
    signature: str
    body: str


# ----------------------------
# Helpers
# ----------------------------
def _read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _node_text(source_bytes: bytes, node) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _one_line(s: str) -> str:
    return " ".join(s.replace("\n", " ").replace("\r", " ").split())


def _walk(node):
    """DFS over tree-sitter nodes."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        for ch in reversed(n.children):
            stack.append(ch)


def load_java_language() -> Language:
    try:
        import tree_sitter_java  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "tree_sitter_java is not available in this Python environment.\n"
            "Run with: modules/ast-extractor/.venv/bin/python ..."
        ) from e

    lang_obj = tree_sitter_java.language() if hasattr(tree_sitter_java, "language") else getattr(tree_sitter_java, "LANGUAGE", None)
    if lang_obj is None:
        raise RuntimeError("tree_sitter_java has no language() / LANGUAGE")

    if isinstance(lang_obj, Language):
        return lang_obj

    # likely PyCapsule
    return Language(lang_obj)

    """
    Load Java language via prebuilt `tree_sitter_java`.

    Depending on versions:
      - tree_sitter_java.language() may return a Language OR a PyCapsule.
      - Parser expects a tree_sitter.Language.
    """
    try:
        import tree_sitter_java  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "tree_sitter_java is not available in this Python environment.\n"
            "Fix: pip install tree_sitter tree_sitter_java (in the same venv)."
        ) from e

    # Most common: function exists
    if hasattr(tree_sitter_java, "language"):
        lang_obj = tree_sitter_java.language()
    elif hasattr(tree_sitter_java, "LANGUAGE"):
        lang_obj = tree_sitter_java.LANGUAGE
    else:
        raise RuntimeError("tree_sitter_java loaded but no language() / LANGUAGE found.")

    # If it's already a Language instance, return it
    if isinstance(lang_obj, Language):
        return lang_obj

    # Otherwise it's likely a PyCapsule; wrap it
    try:
        return Language(lang_obj)
    except Exception as e:
        raise RuntimeError(
            f"Could not construct tree_sitter.Language from tree_sitter_java output: {type(lang_obj)}"
        ) from e

def _set_parser_language(parser: Parser, language: Language) -> None:
    # tree_sitter versions differ:
    # - newer: parser.set_language(language)
    # - older: parser.language = language
    if hasattr(parser, "set_language"):
        parser.set_language(language)  # type: ignore[attr-defined]
    else:
        parser.language = language  # type: ignore[attr-defined]
         

    """
    tree_sitter Parser API differs across versions:
      - Some use parser.set_language(lang)
      - Some use parser.language = lang
    """
    if hasattr(parser, "set_language"):
        parser.set_language(language)  # type: ignore[attr-defined]
    else:
        parser.language = language  # type: ignore[attr-defined]


def find_java_files(root_dir: str) -> List[str]:
    out: List[str] = []
    for base, _, files in os.walk(root_dir):
        for fn in files:
            if fn.endswith(".java"):
                out.append(os.path.join(base, fn))
    return out


def _enclosing_class_name(method_node, source_bytes: bytes) -> Optional[str]:
    """Find closest enclosing class_declaration identifier."""
    cur = method_node
    while cur is not None:
        if cur.type == "class_declaration":
            for ch in cur.children:
                if ch.type == "identifier":
                    return _node_text(source_bytes, ch)
            return None
        cur = cur.parent
    return None


def _extract_name(node, source_bytes: bytes) -> str:
    """Method/constructor name = first identifier child (best-effort)."""
    for ch in node.children:
        if ch.type == "identifier":
            return _node_text(source_bytes, ch)
    return "<unknown>"


def _extract_signature(node, source_bytes: bytes) -> str:
    """
    Build compact signature string:
      - name + formal_parameters
    """
    name = None
    params = None
    for ch in node.children:
        if ch.type == "identifier" and name is None:
            name = _node_text(source_bytes, ch)
        if ch.type == "formal_parameters" and params is None:
            params = _node_text(source_bytes, ch)

    if not name:
        name = "<unknown>"
    if not params:
        params = "()"
    return _one_line(f"{name}{params}")


def _extract_body(node, source_bytes: bytes) -> str:
    """
    For method/constructor, body is usually a child "block".
    Interface/abstract methods may not have one.
    """
    for ch in node.children:
        if ch.type == "block":
            return _node_text(source_bytes, ch)
    return ""


def extract_methods_from_java_file(parser: Parser, file_path: str, include_body: bool) -> List[ExtractedMethod]:
    source_bytes = _read_file_bytes(file_path)
    tree = parser.parse(source_bytes)
    root = tree.root_node

    out: List[ExtractedMethod] = []

    for node in _walk(root):
        if node.type not in ("method_declaration", "constructor_declaration"):
            continue

        kind = "constructor" if node.type == "constructor_declaration" else "method"
        class_name = _enclosing_class_name(node, source_bytes)
        name = _extract_name(node, source_bytes)
        signature = _extract_signature(node, source_bytes)

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        body = _extract_body(node, source_bytes) if include_body else ""

        out.append(
            ExtractedMethod(
                file=file_path,
                class_name=class_name,
                method_name=name,
                kind=kind,
                start_line=start_line,
                end_line=end_line,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                signature=signature,
                body=body,
            )
        )

    return out


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Root directory to scan for .java files")
    ap.add_argument("--out", required=True, help="Output JSON file path")
    ap.add_argument("--no-body", action="store_true", help="Do not include method body text")
    args = ap.parse_args()

    java_lang = load_java_language()
    parser = Parser()
    _set_parser_language(parser, java_lang)

    java_files = find_java_files(args.root)

    all_methods: List[Dict[str, Any]] = []
    for fp in java_files:
        methods = extract_methods_from_java_file(parser, fp, include_body=(not args.no_body))
        all_methods.extend([asdict(m) for m in methods])

    payload = {
        "root": args.root,
        "java_file_count": len(java_files),
        "method_count": len(all_methods),
        "methods": all_methods,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote: {args.out}")
    print(f"Java files: {len(java_files)}")
    print(f"Methods: {len(all_methods)}")


if __name__ == "__main__":
    main()