# ast-extractor (Module 1)

This module extracts AST-like records from a repository. In this skeleton, parsing is implemented as a placeholder; it will be replaced with real Tree-sitter parsing in the next iteration.

## Install (dev)

From `modules/ast-extractor`:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e ".[dev]"
```

## Run

```bash
ast-extract --help
```

### Example (local fixture)

```bash
ast-extract --repo fixtures/tiny_repo --out out.jsonl --languages python
cat out.jsonl
```

## Tests

```bash
pytest -q
```
