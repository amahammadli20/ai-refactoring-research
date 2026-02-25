#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


# ----------------------------
# Utilities
# ----------------------------

def _read_text(path_or_dash: str) -> str:
    if path_or_dash == "-":
        return sys.stdin.read()
    return Path(path_or_dash).read_text(encoding="utf-8", errors="replace")


def _write_text(path_or_dash: str, text: str) -> None:
    if path_or_dash == "-":
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    Path(path_or_dash).parent.mkdir(parents=True, exist_ok=True)
    Path(path_or_dash).write_text(text, encoding="utf-8")


def _run(cmd: list[str], *, cwd: Optional[str] = None, input_text: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _is_git_repo(path: str) -> bool:
    p = Path(path)
    return (p / ".git").exists() or _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path).returncode == 0


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ----------------------------
# Snippet selection
# ----------------------------

def _make_snippet(full_text: str, *, lines: int, mode: str) -> str:
    """
    mode: head | tail | center
    """
    all_lines = full_text.splitlines()
    if lines <= 0 or lines >= len(all_lines):
        return full_text

    if mode == "head":
        return "\n".join(all_lines[:lines]) + "\n"
    if mode == "tail":
        return "\n".join(all_lines[-lines:]) + "\n"
    if mode == "center":
        mid = len(all_lines) // 2
        half = lines // 2
        start = max(0, mid - half)
        end = min(len(all_lines), start + lines)
        start = max(0, end - lines)
        return "\n".join(all_lines[start:end]) + "\n"

    return "\n".join(all_lines[:lines]) + "\n"


# ----------------------------
# Prompt building
# ----------------------------

def _prompt_for_code(language: str, code: str) -> str:
    return (
        "You are a senior software engineer.\n"
        "Refactor the following code to improve readability/structure, while preserving behavior.\n"
        "Do NOT add commentary.\n"
        "Do NOT change public API: do not change method signatures, parameter types, return types, visibility, or thrown exceptions.\n"
        "Do NOT delete large parts of the file.\n"
        "If you cannot refactor safely, return the original code unchanged.\n"
        "Return ONLY the refactored code.\n\n"
        f"LANGUAGE: {language}\n"
        "CODE:\n"
        f"{code}\n"
    )


def _prompt_for_code_with_header_lock(language: str, full_code: str, *, lock_lines: int = 80) -> str:
    """
    For diff-from-code mode: ask model to keep header, but we ALSO enforce it in post-processing.
    """
    lines = full_code.splitlines()
    header = "\n".join(lines[:lock_lines]) + ("\n" if lines else "")
    body = "\n".join(lines[lock_lines:]) + ("\n" if len(lines) > lock_lines else "")

    return (
        "You are a senior software engineer.\n"
        "Refactor the Java file to improve readability/structure while preserving behavior.\n"
        "ABSOLUTE RULES:\n"
        f"1) The first {lock_lines} lines are LOCKED. You MUST copy them EXACTLY as-is.\n"
        "2) Do NOT add commentary.\n"
        "3) Do NOT change public API: no signature/visibility/throws changes.\n"
        "4) Do NOT delete large parts of the file.\n"
        "5) Output ONLY the full updated file content (the entire file, including the locked header).\n\n"
        f"LANGUAGE: {language}\n\n"
        "LOCKED HEADER (copy exactly):\n"
        f"{header}\n"
        "BODY TO REFACTOR:\n"
        f"{body}\n"
    )


def _prompt_for_diff(*, language: str, rel_path: str, code: str) -> str:
    return (
        "You are a senior software engineer.\n"
        "Task: perform a behavior-preserving refactor.\n"
        "Output format rules (MANDATORY):\n"
        "1) Output ONLY a unified diff for a single file.\n"
        "2) The first line MUST be: diff --git a/<path> b/<path>\n"
        "3) Do NOT use markdown fences (```), do NOT add any explanation.\n"
        "4) Do NOT change public API unless absolutely required (prefer no signature changes).\n"
        "5) Preserve semantics. Refactor only.\n"
        "6) The ---/+++ lines MUST be exactly: --- a/<path> and +++ b/<path> (no timestamps).\n"
        "7) Each hunk header must be valid unified diff.\n"
        "8) DO NOT change method signatures, parameter types, return types, visibility, or thrown exceptions.\n"
        "9) If you cannot refactor without changing signatures, output a diff with NO CHANGES.\n\n"
        f"LANGUAGE: {language}\n"
        f"FILE: {rel_path}\n\n"
        "CURRENT FILE CONTENT:\n"
        f"{code}\n"
    )


# ----------------------------
# Diff extraction / sanitization (used in --mode diff)
# ----------------------------

_ALLOWED_PATCH_LINE = re.compile(
    r"""^(
        diff\ --git\ .+|
        index\ [0-9a-f]+\.\.[0-9a-f]+.*|
        ---\ .+|
        \+\+\+\ .+|
        @@\ -\d+(?:,\d+)?\ \+\d+(?:,\d+)?\ @@(?:\ .*)?$|
        [ +\-].*|
        \\ No newline at end of file
    )$""",
    re.VERBOSE,
)

_HUNK_HEADER_FULL = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if "```" not in t:
        return t
    t = re.sub(r"```[a-zA-Z0-9_-]*\n", "", t)
    t = t.replace("```", "")
    return t.strip()


def _rewrite_file_headers(lines: list[str], rel_path: str) -> list[str]:
    out: list[str] = []
    for line in lines:
        if line.startswith("--- "):
            out.append(f"--- a/{rel_path}")
            continue
        if line.startswith("+++ "):
            out.append(f"+++ b/{rel_path}")
            continue
        out.append(line)
    return out


def _fix_unprefixed_hunk_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    in_hunk = False

    for line in lines:
        if line.startswith("@@"):
            in_hunk = True
            out.append(line)
            continue

        if line.startswith(("diff --git ", "index ", "--- ", "+++ ")):
            in_hunk = False
            out.append(line)
            continue

        if in_hunk:
            if line == "" or line.startswith((" ", "+", "-", "\\ No newline")):
                out.append(line)
            else:
                out.append(" " + line)
        else:
            out.append(line)

    return out


def _validate_hunk_counts(diff_text: str) -> bool:
    lines = diff_text.splitlines()
    i = 0

    while i < len(lines):
        m = _HUNK_HEADER_FULL.match(lines[i])
        if not m:
            i += 1
            continue

        old_count = int(m.group(2) or "1")
        new_count = int(m.group(4) or "1")

        old_seen = 0
        new_seen = 0
        i += 1

        while i < len(lines) and not lines[i].startswith("@@ "):
            ln = lines[i]

            if ln.startswith(("diff --git ", "index ", "--- ", "+++ ")):
                return False

            if ln.startswith("\\ No newline"):
                i += 1
                continue

            if ln.startswith("+"):
                new_seen += 1
            elif ln.startswith("-"):
                old_seen += 1
            else:
                if not ln.startswith(" "):
                    return False
                old_seen += 1
                new_seen += 1

            i += 1

        if old_seen != old_count or new_seen != new_count:
            return False

    return True


def _extract_unified_diff(raw: str, *, rel_path: str) -> tuple[Optional[str], Optional[str]]:
    if not raw:
        return None, None

    cleaned = _normalize_newlines(_strip_code_fences(raw))

    lines = cleaned.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.startswith("diff --git "):
            start_idx = i
            break
    if start_idx is None:
        return None, None

    candidate_lines = lines[start_idx:]
    candidate_lines = _rewrite_file_headers(candidate_lines, rel_path=rel_path)
    candidate_lines = _fix_unprefixed_hunk_lines(candidate_lines)

    candidate = "\n".join(candidate_lines).strip() + "\n"

    kept: list[str] = []
    seen_hunk = False
    seen_file_header = False
    seen_minus = False
    seen_plus = False

    for line in candidate_lines:
        if line.strip() == "":
            kept.append(line)
            continue

        if line.startswith("--- "):
            seen_minus = True
        if line.startswith("+++ "):
            seen_plus = True
        if seen_minus and seen_plus:
            seen_file_header = True

        if line.startswith("@@"):
            if not seen_file_header:
                break
            seen_hunk = True

        if not _ALLOWED_PATCH_LINE.match(line):
            break

        kept.append(line)

    diff_text = "\n".join(kept).strip()
    if not diff_text.startswith("diff --git "):
        return None, candidate

    if f"--- a/{rel_path}" not in diff_text or f"+++ b/{rel_path}" not in diff_text or "@@" not in diff_text:
        return None, candidate
    if not seen_hunk:
        return None, candidate
    if not _validate_hunk_counts(diff_text):
        return None, candidate

    return diff_text + "\n", candidate


# ----------------------------
# Diff-from-code helpers + guardrails
# ----------------------------

def _make_unified_diff(*, rel_path: str, old_text: str, new_text: str) -> str:
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
        lineterm="\n",
        n=3,
    )

    header = f"diff --git a/{rel_path} b/{rel_path}\n"
    return header + "".join(diff_lines)


def _diff_add_del(diff_text: str) -> tuple[int, int]:
    add = 0
    delete = 0
    in_hunk = False
    for line in diff_text.splitlines():
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
        if line.startswith("+"):
            add += 1
        elif line.startswith("-"):
            delete += 1
    return add, delete


def _enforce_header_lock(*, original: str, model_code: str, lock_lines: int) -> str:
    """
    Force the top N lines of the output to match the original file exactly.
    This fixes models that drop/alter package/license/imports.
    """
    orig_lines = original.splitlines()
    locked = orig_lines[: max(0, lock_lines)]

    model_lines = model_code.splitlines()
    # If model returned a full file, drop its first lock_lines and keep the rest as body.
    # If model returned a short fragment, treat it as body.
    body = model_lines[lock_lines:] if len(model_lines) >= lock_lines else model_lines

    final_lines = locked + body
    return "\n".join(final_lines).rstrip() + "\n"


def _guardrail_check(
    *,
    rel_path: str,
    original: str,
    new_code: str,
    diff_text: str,
    max_deletions: int,
    max_deletion_ratio: float,
    require_package: bool,
    require_license: bool,
    require_class_name: bool,
) -> tuple[bool, str]:
    if require_package and "package " not in new_code:
        return False, "guardrail_failed: missing package declaration"

    if require_license:
        if "Apache Software Foundation" in original and "Apache Software Foundation" not in new_code:
            return False, "guardrail_failed: license header removed"

    if require_class_name:
        base = Path(rel_path).name.replace(".java", "")
        if f"class {base}" in original and f"class {base}" not in new_code:
            return False, f"guardrail_failed: missing class {base}"

    _, deleted = _diff_add_del(diff_text)
    orig_lines = max(1, len(original.splitlines()))
    del_ratio = deleted / orig_lines

    if deleted > max_deletions:
        return False, f"guardrail_failed: too many deletions ({deleted} > {max_deletions})"
    if del_ratio > max_deletion_ratio:
        return False, f"guardrail_failed: deletion ratio too high ({del_ratio:.2%} > {max_deletion_ratio:.2%})"

    return True, ""


def _git_apply_check(diff_text: str, *, git_root: str) -> tuple[bool, str]:
    proc = _run(["git", "apply", "--check", "-"], cwd=git_root, input_text=diff_text)
    return proc.returncode == 0, proc.stderr.strip()


# ----------------------------
# Ollama call
# ----------------------------

def _ollama_run(model: str, prompt: str) -> tuple[bool, str, str]:
    proc = _run(["ollama", "run", model], input_text=prompt)
    ok = proc.returncode == 0
    return ok, proc.stdout, proc.stderr


# ----------------------------
# Output schema
# ----------------------------

@dataclass
class Result:
    ok: bool
    error: Optional[str]
    model: str
    raw: str
    code: Optional[str]
    diff: Optional[str]
    candidate_diff: Optional[str]
    meta: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "error": self.error,
                "model": self.model,
                "raw": self.raw,
                "code": self.code,
                "diff": self.diff,
                "candidate_diff": self.candidate_diff,
                "meta": self.meta,
            },
            indent=2,
            ensure_ascii=False,
        )


# ----------------------------
# CLI
# ----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="local_llm", description="Local refactor helper using Ollama.")
    p.add_argument("--model", default="deepseek-coder:6.7b", help="Ollama model name.")
    p.add_argument("--mode", choices=["code", "diff", "diff-from-code"], default="code", help="Output mode.")
    p.add_argument("--path", default="", help="Repo-relative file path (used in diff headers).")
    p.add_argument("--in", dest="in_path", required=True, help="Input file path or '-' for stdin.")
    p.add_argument("--out", dest="out_path", required=True, help="Output JSON path or '-' for stdout.")

    p.add_argument("--language", default="java", help="Language label for the prompt.")
    p.add_argument("--retries", type=int, default=2, help="How many times to retry on non-diff / invalid output.")
    p.add_argument("--git-root", default="", help="If set, run 'git apply --check' in this directory.")
    p.add_argument("--snippet-lines", type=int, default=0, help="If >0, send only N lines to the model.")
    p.add_argument("--snippet-mode", choices=["head", "tail", "center"], default="head", help="Where to take snippet from.")

    # Guardrails for diff-from-code
    p.add_argument("--max-deletions", type=int, default=80, help="Reject if diff deletes more than N lines (diff-from-code).")
    p.add_argument("--max-deletion-ratio", type=float, default=0.30, help="Reject if deletions/original_lines exceed this ratio (diff-from-code).")
    p.add_argument("--require-package", action="store_true", help="Require a 'package ' declaration in output code (diff-from-code).")
    p.add_argument("--require-license", action="store_true", help="Require Apache license header phrase to remain if it existed (diff-from-code).")
    p.add_argument("--require-class-name", action="store_true", help="Require primary class name (from filename) to remain (diff-from-code).")

    # Header lock for diff-from-code (also enforced in post-processing)
    p.add_argument("--header-lock-lines", type=int, default=120, help="For diff-from-code: number of top lines to lock verbatim.")

    return p


def main() -> int:
    args = build_parser().parse_args()

    original = _read_text(args.in_path)
    text_for_model = original

    if args.snippet_lines and args.snippet_lines > 0:
        text_for_model = _make_snippet(original, lines=int(args.snippet_lines), mode=str(args.snippet_mode))

    rel_path = args.path.strip() or (args.in_path if args.in_path != "-" else "unknown.java")
    rel_path = rel_path.replace("\\", "/")

    # Prompt selection
    if args.mode == "code":
        prompt = _prompt_for_code(args.language, text_for_model)
    elif args.mode == "diff":
        prompt = _prompt_for_diff(language=args.language, rel_path=rel_path, code=text_for_model)
    else:  # diff-from-code
        prompt = _prompt_for_code_with_header_lock(args.language, text_for_model, lock_lines=int(args.header_lock_lines))

    git_root = args.git_root.strip()
    if git_root and not _is_git_repo(git_root):
        res = Result(
            ok=False,
            error=f"--git-root is not a git repo: {git_root}",
            model=args.model,
            raw="",
            code=None,
            diff=None,
            candidate_diff=None,
            meta={"path": rel_path},
        )
        _write_text(args.out_path, res.to_json())
        return 2

    last_raw = ""
    last_candidate = None
    last_diff = None
    last_err = None

    attempts = max(1, int(args.retries) + 1)

    for attempt in range(1, attempts + 1):
        ok, out, err = _ollama_run(args.model, prompt)
        raw = (out or "").strip()
        last_raw = raw

        if not ok:
            last_err = f"ollama_failed: {err.strip()}"
            continue

        # ---- MODE: code ----
        if args.mode == "code":
            code = _strip_code_fences(raw).strip() + "\n"
            res = Result(
                ok=True,
                error=None,
                model=args.model,
                raw=raw,
                code=code,
                diff=None,
                candidate_diff=None,
                meta={"path": rel_path, "attempt": attempt, "snippet_lines": args.snippet_lines, "snippet_mode": args.snippet_mode},
            )
            _write_text(args.out_path, res.to_json())
            return 0

        # ---- MODE: diff-from-code ----
        if args.mode == "diff-from-code":
            model_code = _strip_code_fences(raw).strip() + "\n"

            # Enforce header lock regardless of model compliance
            new_code = _enforce_header_lock(
                original=original,
                model_code=model_code,
                lock_lines=int(args.header_lock_lines),
            )

            diff_text = _make_unified_diff(rel_path=rel_path, old_text=original, new_text=new_code)

            ok_guard, guard_err = _guardrail_check(
                rel_path=rel_path,
                original=original,
                new_code=new_code,
                diff_text=diff_text,
                max_deletions=int(args.max_deletions),
                max_deletion_ratio=float(args.max_deletion_ratio),
                require_package=bool(args.require_package),
                require_license=bool(args.require_license),
                require_class_name=bool(args.require_class_name),
            )
            if not ok_guard:
                last_err = guard_err
                continue

            if git_root:
                ok_apply, apply_err = _git_apply_check(diff_text, git_root=git_root)
                if not ok_apply:
                    last_err = f"git_apply_failed: {apply_err}"
                    continue

            res = Result(
                ok=True,
                error=None,
                model=args.model,
                raw=raw,
                code=new_code,
                diff=diff_text,
                candidate_diff=diff_text,
                meta={
                    "path": rel_path,
                    "attempt": attempt,
                    "snippet_lines": args.snippet_lines,
                    "snippet_mode": args.snippet_mode,
                    "git_root": git_root or None,
                    "max_deletions": int(args.max_deletions),
                    "max_deletion_ratio": float(args.max_deletion_ratio),
                    "require_package": bool(args.require_package),
                    "require_license": bool(args.require_license),
                    "require_class_name": bool(args.require_class_name),
                    "header_lock_lines": int(args.header_lock_lines),
                },
            )
            _write_text(args.out_path, res.to_json())
            return 0

        # ---- MODE: diff ----
        diff_text, candidate = _extract_unified_diff(raw, rel_path=rel_path)
        last_candidate = candidate
        last_diff = diff_text

        if diff_text is None:
            last_err = "no_clean_diff: Model did not return a clean unified diff (or failed validation). Try changing snippet/head/tail/center or increase retries."
            continue

        if git_root:
            ok_apply, apply_err = _git_apply_check(diff_text, git_root=git_root)
            if not ok_apply:
                last_err = f"git_apply_failed: {apply_err}"
                continue

        res = Result(
            ok=True,
            error=None,
            model=args.model,
            raw=raw,
            code=None,
            diff=diff_text,
            candidate_diff=candidate,
            meta={"path": rel_path, "attempt": attempt, "snippet_lines": args.snippet_lines, "snippet_mode": args.snippet_mode, "git_root": git_root or None},
        )
        _write_text(args.out_path, res.to_json())
        return 0

    res = Result(
        ok=False,
        error=last_err or "unknown_error",
        model=args.model,
        raw=last_raw,
        code=None,
        diff=last_diff,
        candidate_diff=last_candidate,
        meta={"path": rel_path, "attempts": attempts, "snippet_lines": args.snippet_lines, "snippet_mode": args.snippet_mode, "git_root": git_root or None},
    )
    _write_text(args.out_path, res.to_json())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())