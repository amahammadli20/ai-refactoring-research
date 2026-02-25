#!/usr/bin/env python3
from __future__ import annotations
import sys
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def diff_stats(diff_text: str) -> Tuple[int, int]:
    add = 0
    delete = 0
    in_hunk = False
    for line in (diff_text or "").splitlines():
        if line.startswith("@@"):
            in_hunk = True
            continue
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if not in_hunk:
            continue
        if line.startswith(("+++ ", "--- ")):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            add += 1
        elif line.startswith("-") and not line.startswith("---"):
            delete += 1
    return add, delete


def run_local_llm(local_llm_path: str, *, model: str, rel_path: str, src_text: str, retries: int) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        in_file = td / "Before.java"
        out_json = td / "out.json"
        in_file.write_text(src_text, encoding="utf-8")

        cmd = [
            sys.executable, local_llm_path,
            "--mode", "diff-from-code",
            "--model", model,
            "--path", rel_path,
            "--retries", str(retries),
            "--max-deletions", "120",
            "--max-deletion-ratio", "0.30",
            "--in", str(in_file),
            "--out", str(out_json),
        ]

        proc = subprocess.run(cmd, text=True, capture_output=True)
        if not out_json.exists():
            return {
                "ok": False,
                "error": f"runner_failed: no out.json produced. rc={proc.returncode}",
                "_stderr_tail": (proc.stderr or "")[-800:],
            }

        res = json.loads(out_json.read_text(encoding="utf-8"))
        res["_runner"] = {
            "cmd": cmd,
            "rc": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-800:],
            "stderr_tail": (proc.stderr or "")[-800:],
        }
        return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="Path to pure_refactoring_data.json")
    ap.add_argument("--local-llm", required=True, help="Path to scripts/local_llm.py")
    ap.add_argument("--model", default="deepseek-coder:1.3b")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--retries", type=int, default=0)
    ap.add_argument("--out", default="results_offline.jsonl")
    ap.add_argument("--project", default="", help="Optional: filter by projectName (e.g., commons-io)")
    args = ap.parse_args()

    data = load_json(args.dataset)
    out_path = Path(args.out)

    n = 0
    ok_count = 0

    with out_path.open("w", encoding="utf-8") as w:
        for row in data:
            if args.project and row.get("projectName") != args.project:
                continue

            before = row.get("sourceCodeBeforeRefactoring") or ""
            after = row.get("sourceCodeAfterRefactoring") or ""

            rel_path = (row.get("filePathBefore") or "Example.java").lstrip("/")

            if not before.strip() or not after.strip():
                continue

            res = run_local_llm(
                args.local_llm,
                model=args.model,
                rel_path=rel_path,
                src_text=before,
                retries=args.retries,
            )

            add, delete = diff_stats(res.get("diff") or "")

            record = {
                "projectName": row.get("projectName"),
                "commitId": row.get("commitId"),
                "filePathBefore": row.get("filePathBefore"),
                "methodNameBefore": row.get("methodNameBefore"),
                "ok": bool(res.get("ok")),
                "error": res.get("error"),
                "diff_add": add,
                "diff_del": delete,
            }
            w.write(json.dumps(record, ensure_ascii=False) + "\n")
            w.flush()

            n += 1
            if record["ok"]:
                ok_count += 1

            print(f"[{n}/{args.limit}] ok={record['ok']} add={add} del={delete} err={record['error']}")
            if n >= args.limit:
                break

    print(f"\nWrote: {out_path}")
    print(f"OK: {ok_count}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
