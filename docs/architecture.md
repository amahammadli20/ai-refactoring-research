# Architecture

Monorepo with independent modules under `modules/`.

## Module 1: AST Extractor
Pipeline:
1) ingest repo (clone or local path)
2) scan files (include/exclude, detect language)
3) parse (Tree-sitter placeholder in this skeleton)
4) serialize AST
5) write JSONL (one record per file)
