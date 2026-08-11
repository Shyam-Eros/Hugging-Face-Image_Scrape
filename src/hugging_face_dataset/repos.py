"""Load Hugging Face repo list from repository.txt."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from hugging_face_dataset.paths import PROJECT_ROOT

HINT_RE = re.compile(r"\(([^)]+)\)")


@dataclass(frozen=True)
class RepoEntry:
    repo_id: str
    hint: str = ""


def parse_repo_line(line: str) -> RepoEntry | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.isdigit():
        return None
    if "#" in line:
        line = line.split("#", 1)[0].strip()
    hint = ""
    m = HINT_RE.search(line)
    if m:
        hint = m.group(1).strip().lower()
        line = HINT_RE.sub("", line).strip()
    line = line.strip()
    if not line or "/" not in line:
        return None
    return RepoEntry(repo_id=line, hint=hint)


def load_repos(path: Path | None = None) -> list[RepoEntry]:
    path = path or (PROJECT_ROOT / "repository.txt")
    if not path.exists():
        return []
    entries: list[RepoEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = parse_repo_line(line)
        if entry:
            entries.append(entry)
    return entries


def repo_slug(repo_id: str) -> str:
    return repo_id.split("/", 1)[-1]
