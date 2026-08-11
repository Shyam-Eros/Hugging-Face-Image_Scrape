"""Dataset profile produced by inspection."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class DatasetProfile:
    repo_id: str
    strategy: str
    image_columns: list[str] = field(default_factory=lambda: ["jpg"])
    url_columns: list[str] = field(default_factory=list)
    id_columns: list[str] = field(default_factory=lambda: ["uid", "id", "image_id"])
    file_glob: str = "**/*.parquet"
    zip_filename: str = ""
    confidence: float = 0.0
    notes: str = ""

    @property
    def slug(self) -> str:
        return self.repo_id.split("/", 1)[-1]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> DatasetProfile:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)
