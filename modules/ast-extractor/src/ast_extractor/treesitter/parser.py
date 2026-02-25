from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import tree_sitter_java as tsjava
from tree_sitter import Language, Node, Parser


def _node_to_dict(node: Node, max_depth: int, depth: int = 0) -> Dict[str, Any]:
    """
    Serialize a Tree-sitter node into a JSON-friendly dict.

    We keep only named nodes by default (reduces size a lot),
    and apply a max_depth to avoid huge outputs.
    """
    d: Dict[str, Any] = {
        "type": node.type,
        "is_named": node.is_named,
        "start_byte": node.start_byte,
        "end_byte": node.end_byte,
    }

    if depth >= max_depth:
        d["children"] = []
        d["truncated"] = True
        return d

    children = []
    for ch in node.children:
        # Keep only meaningful nodes (named nodes)
        if ch.is_named:
            children.append(_node_to_dict(ch, max_depth=max_depth, depth=depth + 1))

    d["children"] = children
    return d


def parse_file(path: Path, language: str, max_bytes: int, max_depth: int = 35) -> Dict[str, Any]:
    """
    Parse a source file into a Tree-sitter AST (serialized to dict).

    Current implementation supports Java only, using the `tree-sitter-java` package.
    """
    b = path.read_bytes()
    if len(b) > max_bytes:
        raise ValueError(f"File too large: {path} ({len(b)} bytes > {max_bytes})")

    if language != "java":
        raise ValueError(f"Tree-sitter parsing is currently implemented for Java only. Got: {language}")

    # New py-tree-sitter API:
    # - language packages expose `language()`
    # - wrap it with tree_sitter.Language(...)
    JAVA_LANGUAGE = Language(tsjava.language())

    # New Parser API (0.25+): pass language to constructor
    parser = Parser(JAVA_LANGUAGE)

    tree = parser.parse(b)
    root_node = tree.root_node

    return {
        "type": "tree_sitter_ast",
        "language": language,
        "root": _node_to_dict(root_node, max_depth=max_depth),
    }