# Module 01 — AST Extraction

## Goal
Extract syntax trees (AST) from a user-provided repository using Tree-sitter.

## CLI
`ast-extract --repo <url-or-path> --out <file.jsonl> [--ref main] [--languages python] [--include ...] [--exclude ...]`

## Output
JSONL, one record per file:
- repo/ref/commit
- path, language, sha256
- parse_ok, errors
- ast (serialized tree)
