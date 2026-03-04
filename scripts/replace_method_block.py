#!/usr/bin/env python3
import argparse
import json
from tree_sitter import Parser, Language

def load_java_language() -> Language:
    import tree_sitter_java  # installed in modules/ast-extractor/.venv
    lang_obj = tree_sitter_java.language()
    if isinstance(lang_obj, Language):
        return lang_obj
    return Language(lang_obj)  # PyCapsule -> Language

def set_parser_language(parser: Parser, language: Language) -> None:
    if hasattr(parser, "set_language"):
        parser.set_language(language)  # type: ignore[attr-defined]
    else:
        parser.language = language  # type: ignore[attr-defined]

def walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        for ch in reversed(n.children):
            stack.append(ch)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods-json", required=True)
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--new-block-file", required=True, help="File containing ONLY the Java block: { ... }")
    ap.add_argument("--out-file", required=True, help="Write modified source here (safe, no in-place)")
    args = ap.parse_args()

    p = json.load(open(args.methods_json, "r", encoding="utf-8"))
    m = p["methods"][args.index]
    fp = m["file"]

    method_start = int(m["start_byte"])
    method_end = int(m["end_byte"])

    src = open(fp, "rb").read()

    java_lang = load_java_language()
    parser = Parser()
    set_parser_language(parser, java_lang)

    tree = parser.parse(src)
    root = tree.root_node

    target = None
    for node in walk(root):
        if node.type in ("method_declaration", "constructor_declaration"):
            if node.start_byte == method_start and node.end_byte == method_end:
                target = node
                break

    if target is None:
        raise SystemExit(f"Could not locate method node by byte range in: {fp}")

    block = None
    for ch in target.children:
        if ch.type == "block":
            block = ch
            break

    if block is None:
        raise SystemExit("Target method has no block (interface/abstract?)")

    new_block = open(args.new_block_file, "rb").read()

    out = src[:block.start_byte] + new_block + src[block.end_byte:]

    open(args.out_file, "wb").write(out)
    print("Wrote:", args.out_file)
    print("Original:", fp)
    print("Replaced block bytes:", block.start_byte, block.end_byte)

if __name__ == "__main__":
    main()
