from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple
import re

from git import Repo  # GitPython


@dataclass(frozen=True)
class RepoMeta:
    repo: str
    ref: Optional[str]
    commit: Optional[str]


def _is_git_url(s: str) -> bool:
    return bool(re.match(r"^https?://", s)) or s.endswith(".git")


def materialize_repo(repo: str, ref: Optional[str]) -> Tuple[Path, Dict]:
    """Materialize a repo locally.

    - If `repo` is a local directory, it is used directly.
    - If `repo` is a git URL, it is cloned to `.cache/repos/<safe_name>` and optionally checked out.

    Returns: (local_repo_path, metadata_dict)
    """
    p = Path(repo)
    if p.exists() and p.is_dir():
        return p.resolve(), asdict(RepoMeta(repo=str(p.resolve()), ref=None, commit=None))

    if not _is_git_url(repo):
        raise ValueError(f"--repo must be a local dir or a git URL. Got: {repo}")

    cache_root = Path(".cache/repos")
    cache_root.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", repo)
    local_path = (cache_root / safe_name).resolve()

    if local_path.exists():
        r = Repo(str(local_path))
        r.remotes.origin.fetch()
    else:
        r = Repo.clone_from(repo, str(local_path))

    if ref:
        r.git.checkout(ref)

    commit = None
    try:
        commit = r.head.commit.hexsha
    except Exception:
        commit = None

    return local_path, asdict(RepoMeta(repo=repo, ref=ref, commit=commit))
