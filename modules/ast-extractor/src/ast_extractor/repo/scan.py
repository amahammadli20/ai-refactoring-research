from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import fnmatch

from ast_extractor.config import EXT_TO_LANG
from ast_extractor.utils.hashing import sha256_file


def _matches_any(path: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def scan_files(
    repo_path: Path,
    languages: List[str],
    include: List[str],
    exclude: List[str],
    max_files: int,
) -> List[Dict]:
    repo_path = repo_path.resolve()
    results: List[Dict] = []

    for abs_path in repo_path.rglob("*"):
        if not abs_path.is_file():
            continue

        rel_path = abs_path.relative_to(repo_path).as_posix()

        if exclude and _matches_any(rel_path, exclude):
            continue
        if include and not _matches_any(rel_path, include):
            continue

        ext = abs_path.suffix.lower()
        lang = EXT_TO_LANG.get(ext)
        if not lang:
            continue
        if languages and lang not in set(languages):
            continue

        results.append(
            {
                "abs_path": abs_path,
                "rel_path": rel_path,
                "language": lang,
                "sha256": sha256_file(abs_path),
            }
        )

        if len(results) >= max_files:
            break

    return results
