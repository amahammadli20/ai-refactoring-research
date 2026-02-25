import argparse
import json
import sys
from pathlib import Path

from ast_extractor.config import DEFAULT_EXCLUDES, ExtractConfig
from ast_extractor.output.writer import write_jsonl
from ast_extractor.repo.clone import materialize_repo
from ast_extractor.repo.scan import scan_files
from ast_extractor.treesitter.parser import parse_file

# NOTE: Ensure package exists:
#   src/ast_extractor/summary/__init__.py
#   src/ast_extractor/summary/java_summary.py
from ast_extractor.summary.java_summary import summarize_java_ast


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ast-extract",
        description="Extract ASTs from a repository using Tree-sitter.",
    )

    p.add_argument("--repo", required=True, help="GitHub URL or local path.")
    p.add_argument("--ref", default=None, help="Branch/tag/commit to checkout (for git URLs).")
    p.add_argument("--out", required=True, help="Output JSONL path.")

    p.add_argument(
        "--languages",
        default="auto",
        help="Comma-separated list (e.g., java,python,javascript) or 'auto'.",
    )
    p.add_argument("--include", action="append", default=[], help="Glob include (repeatable).")
    p.add_argument("--exclude", action="append", default=[], help="Glob exclude (repeatable).")

    p.add_argument("--fail-fast", action="store_true", help="Stop on first parse error.")
    p.add_argument("--max-files", type=int, default=10_000, help="Max files to parse.")
    p.add_argument("--max-bytes", type=int, default=2_000_000, help="Max bytes per file.")
    p.add_argument(
        "--max-depth",
        type=int,
        default=25,
        help="Max AST depth to serialize (prevents huge outputs).",
    )

    p.add_argument("--no-ast", action="store_true", help="Do not include full AST in output.")
    p.add_argument("--summary", action="store_true", help="Include a compact summary for each file.")
    p.add_argument(
        "--summary-only",
        action="store_true",
        help="Output only summary (implies --summary and --no-ast).",
    )

    return p


def _resolve_languages(arg: str) -> list[str]:
    if arg.strip().lower() == "auto":
        return []
    return [x.strip().lower() for x in arg.split(",") if x.strip()]


def _default_includes(languages: list[str]) -> list[str]:
    """
    If user didn't provide --include, choose a sensible default.
    Prevents common 'Files scanned: 0' surprises.
    """
    if not languages:
        return ["**/*"]
    if "java" in languages:
        return ["**/*.java"]
    return ["**/*"]


def _generic_summary(ast: dict, language: str, max_depth_limit: int | None) -> dict:
    root = ast.get("root") if isinstance(ast, dict) else None
    return {
        "kind": "generic_summary",
        "language": language,
        "root_type": root.get("type") if isinstance(root, dict) else None,
        "serialized_depth_limit": max_depth_limit,
    }


def main() -> int:
    args = build_parser().parse_args()

    # normalize implied flags
    if args.summary_only:
        args.summary = True
        args.no_ast = True

    languages = _resolve_languages(args.languages)
    includes = args.include if args.include else _default_includes(languages)

    cfg = ExtractConfig(
        repo=args.repo,
        ref=args.ref,
        out=args.out,
        languages=languages,
        include=includes,
        exclude=(args.exclude or []) + DEFAULT_EXCLUDES,
        fail_fast=bool(args.fail_fast),
        max_files=int(args.max_files),
        max_bytes=int(args.max_bytes),
    )

    repo_path, meta = materialize_repo(cfg.repo, cfg.ref)
    files = scan_files(repo_path, cfg.languages, cfg.include, cfg.exclude, cfg.max_files)

    records = []
    for f in files:
        try:
            ast = parse_file(
                f["abs_path"],
                language=f["language"],
                max_bytes=cfg.max_bytes,
                max_depth=int(args.max_depth),
            )

            summary = None
            if args.summary:
                if f["language"] == "java" and isinstance(ast, dict):
                    summary = summarize_java_ast(ast, max_depth_limit=int(args.max_depth))
                else:
                    summary = _generic_summary(ast, f["language"], int(args.max_depth))

            rec = {
                **meta,
                "path": f["rel_path"],
                "language": f["language"],
                "sha256": f["sha256"],
                "parse_ok": True,
                "errors": [],
                "summary": summary,
                "ast": None if args.no_ast else ast,
            }

        except Exception as e:
            rec = {
                **meta,
                "path": f.get("rel_path"),
                "language": f.get("language"),
                "sha256": f.get("sha256"),
                "parse_ok": False,
                "errors": [str(e)],
                "summary": None,
                "ast": None,
            }

            if cfg.fail_fast:
                out_path = Path(cfg.out)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                write_jsonl(out_path, [rec])
                print(json.dumps(rec, indent=2), file=sys.stderr)
                return 2

        records.append(rec)

    out_path = Path(cfg.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_path, records)

    print(f"Repo path: {repo_path}")
    print(f"Files scanned: {len(files)}")
    print(f"Wrote JSONL: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())