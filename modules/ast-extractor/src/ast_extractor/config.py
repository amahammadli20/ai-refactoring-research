from dataclasses import dataclass
from typing import List, Optional

DEFAULT_EXCLUDES = [
    "**/.git/**",
    "**/node_modules/**",
    "**/dist/**",
    "**/build/**",
    "**/target/**",
    "**/__pycache__/**",
]

EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
}

@dataclass(frozen=True)
class ExtractConfig:
    repo: str
    ref: Optional[str]
    out: str
    languages: List[str]
    include: List[str]
    exclude: List[str]
    fail_fast: bool = False
    max_files: int = 10_000
    max_bytes: int = 2_000_000  # per file
