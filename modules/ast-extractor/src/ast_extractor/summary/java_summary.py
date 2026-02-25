from __future__ import annotations

from collections import Counter
from typing import Any, Dict


JAVA_CONTROL_FLOW_TYPES = {
    "if_statement",
    "switch_expression",
    "switch_statement",
    "while_statement",
    "do_statement",
    "for_statement",
    "enhanced_for_statement",
    "try_statement",
    "try_with_resources_statement",
    "synchronized_statement",
    "return_statement",
    "throw_statement",
    "break_statement",
    "continue_statement",
    "assert_statement",
    "labeled_statement",
    "yield_statement",
    "ternary_expression",
    "lambda_expression",
}

JAVA_DECL_TYPES = {
    "package_declaration",
    "import_declaration",
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "annotation_type_declaration",
    "record_declaration",
    "method_declaration",
    "constructor_declaration",
    "field_declaration",
    "local_variable_declaration",
    "annotation",
    "marker_annotation",
}

# Helpful but optional nodes for "size-ish" signals
JAVA_EXPR_STMT_TYPES = {
    "expression_statement",
    "assignment_expression",
    "method_invocation",
    "object_creation_expression",
    "binary_expression",
    "unary_expression",
}


def summarize_java_ast(ast: Dict[str, Any], *, max_depth_limit: int | None = None) -> Dict[str, Any]:
    """
    Compact, safe summary for Java Tree-sitter AST JSON.

    - Works on the serialized AST returned by parse_file() (may be depth-limited).
    - Keeps output small but informative for downstream research/analysis.
    - Never raises on malformed inputs; returns an error summary instead.

    Parameters
    ----------
    ast:
        Dict returned by parse_file(...) (expected keys: "root", maybe "type"/"language", etc.)
    max_depth_limit:
        If you pass CLI's --max-depth here, the summary will record it as metadata.
        This is useful to interpret counts when AST serialization is truncated.
    """
    root = ast.get("root") if isinstance(ast, dict) else None
    if not isinstance(root, dict):
        return {
            "kind": "java_summary",
            "error": "missing_root",
            "node_count_total": 0,
            "node_count_named": 0,
            "max_depth_seen": 0,
            "decls_total": 0,
            "control_flow_count": 0,
            "expr_stmt_like_count": 0,
            "top_node_types": [],
            "serialized_depth_limit": max_depth_limit,
        }

    type_counts: Counter[str] = Counter()
    named_nodes = 0
    total_nodes = 0
    max_depth_seen = 0

    def walk(node: Dict[str, Any], depth: int) -> None:
        nonlocal named_nodes, total_nodes, max_depth_seen
        total_nodes += 1
        if depth > max_depth_seen:
            max_depth_seen = depth

        t = node.get("type")
        if isinstance(t, str):
            type_counts[t] += 1

        if node.get("is_named") is True:
            named_nodes += 1

        children = node.get("children") or []
        for ch in children:
            if isinstance(ch, dict):
                walk(ch, depth + 1)

    walk(root, 0)

    # Core declaration counts
    pkg = type_counts.get("package_declaration", 0)
    imports = type_counts.get("import_declaration", 0)

    classes = type_counts.get("class_declaration", 0)
    interfaces = type_counts.get("interface_declaration", 0)
    enums = type_counts.get("enum_declaration", 0)
    records = type_counts.get("record_declaration", 0)
    anno_types = type_counts.get("annotation_type_declaration", 0)

    methods = type_counts.get("method_declaration", 0)
    ctors = type_counts.get("constructor_declaration", 0)
    fields = type_counts.get("field_declaration", 0)
    locals_ = type_counts.get("local_variable_declaration", 0)

    annotations = type_counts.get("annotation", 0) + type_counts.get("marker_annotation", 0)

    control_flow = sum(type_counts.get(t, 0) for t in JAVA_CONTROL_FLOW_TYPES)
    decls_total = sum(type_counts.get(t, 0) for t in JAVA_DECL_TYPES)
    expr_stmt_like = sum(type_counts.get(t, 0) for t in JAVA_EXPR_STMT_TYPES)

    # Keep JSON small but informative
    top_types = type_counts.most_common(25)

    return {
        "kind": "java_summary",
        "root_type": root.get("type"),
        "serialized_depth_limit": max_depth_limit,
        "node_count_total": total_nodes,
        "node_count_named": named_nodes,
        "max_depth_seen": max_depth_seen,
        "decls_total": decls_total,
        "package_decl": pkg,
        "import_count": imports,
        "type_decls": {
            "class": classes,
            "interface": interfaces,
            "enum": enums,
            "record": records,
            "annotation_type": anno_types,
        },
        "member_decls": {
            "methods": methods,
            "constructors": ctors,
            "fields": fields,
            "local_vars": locals_,
        },
        "annotation_count": annotations,
        "control_flow_count": control_flow,
        "expr_stmt_like_count": expr_stmt_like,
        "top_node_types": [{"type": t, "count": c} for (t, c) in top_types],
    }