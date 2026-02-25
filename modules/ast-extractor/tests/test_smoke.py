from pathlib import Path
import json

from ast_extractor.repo.clone import materialize_repo
from ast_extractor.repo.scan import scan_files
from ast_extractor.output.writer import write_jsonl


def test_scan_and_write(tmp_path: Path) -> None:
    repo_path, meta = materialize_repo("fixtures/tiny_repo", ref=None)
    files = scan_files(repo_path, languages=["python"], include=["**/*"], exclude=[], max_files=100)
    assert len(files) >= 2

    out = tmp_path / "out.jsonl"
    records = []
    for f in files:
        records.append({**meta, "path": f["rel_path"], "language": f["language"], "sha256": f["sha256"]})

    write_jsonl(out, records)

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(records)
    _ = json.loads(lines[0])
