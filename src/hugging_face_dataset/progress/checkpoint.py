"""Checkpoint tracking for resumable scraping."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

SHARD_PATH_RE = re.compile(
    r"((?:\d+/least_dim_range=[^\s:]+\.parquet)|(?:data/train-[^\s:]+\.parquet)|(?:data/[^:\s]+\.parquet))"
)

URL_UNIT_PREFIX = "url:"


def normalize_unit_id(unit_id: str) -> str:
    unit_id = unit_id.strip()
    m = SHARD_PATH_RE.search(unit_id)
    if m:
        return m.group(1)
    if ".parquet" in unit_id:
        for marker in ("0/least_dim_range", "data/"):
            idx = unit_id.find(marker)
            if idx >= 0:
                return unit_id[idx:].split()[0]
    return unit_id


def url_unit_id(url_hash: str) -> str:
    return f"{URL_UNIT_PREFIX}{url_hash}"


class ProgressStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stats: dict[str, int] = {"uploaded": 0, "skipped": 0, "failed": 0}
        self._done = self._load()

    def _load(self) -> set[str]:
        done: set[str] = set()
        if not self.path.exists():
            return done
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("status") == "done":
                    unit = rec.get("unit") or rec.get("shard")
                    if unit:
                        done.add(normalize_unit_id(unit))
                for key in ("uploaded", "skipped", "failed"):
                    if key in rec:
                        self._stats[key] = self._stats.get(key, 0) + int(rec[key])
            except json.JSONDecodeError:
                continue
        return done

    def is_done(self, unit_id: str) -> bool:
        return normalize_unit_id(unit_id) in self._done

    def is_url_done(self, url_hash: str) -> bool:
        return url_unit_id(url_hash) in self._done

    def mark_done(
        self,
        unit_id: str,
        *,
        uploaded: int = 0,
        skipped: int = 0,
        failed: int = 0,
    ) -> None:
        unit_id = normalize_unit_id(unit_id)
        if unit_id in self._done:
            return
        self._done.add(unit_id)
        self._append(unit_id, uploaded=uploaded, skipped=skipped, failed=failed)

    def mark_url_done(self, url_hash: str, outcome: str) -> None:
        uid = url_unit_id(url_hash)
        if uid in self._done:
            return
        self._done.add(uid)
        uploaded = 1 if outcome == "uploaded" else 0
        skipped = 1 if outcome == "skipped" else 0
        failed = 1 if outcome == "failed" else 0
        self._append(uid, uploaded=uploaded, skipped=skipped, failed=failed)

    def mark_batch(
        self,
        items: list[tuple[str, str]],
    ) -> None:
        """Checkpoint a batch of (unit_id, outcome) pairs in one append."""
        if not items:
            return
        uploaded = skipped = failed = 0
        with self.path.open("a", encoding="utf-8") as f:
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            for unit_id, outcome in items:
                unit_id = normalize_unit_id(unit_id)
                if unit_id in self._done:
                    continue
                self._done.add(unit_id)
                u = 1 if outcome == "uploaded" else 0
                s = 1 if outcome == "skipped" else 0
                fl = 1 if outcome == "failed" else 0
                uploaded += u
                skipped += s
                failed += fl
                rec = {
                    "unit": unit_id,
                    "status": "done",
                    "outcome": outcome,
                    "uploaded": u,
                    "skipped": s,
                    "failed": fl,
                    "ts": ts,
                }
                f.write(json.dumps(rec) + "\n")
        self._stats["uploaded"] += uploaded
        self._stats["skipped"] += skipped
        self._stats["failed"] += failed

    def _append(
        self,
        unit_id: str,
        *,
        uploaded: int = 0,
        skipped: int = 0,
        failed: int = 0,
    ) -> None:
        rec = {
            "unit": unit_id,
            "status": "done",
            "uploaded": uploaded,
            "skipped": skipped,
            "failed": failed,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        self._stats["uploaded"] += uploaded
        self._stats["skipped"] += skipped
        self._stats["failed"] += failed

    @property
    def completed_count(self) -> int:
        return len(self._done)

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)
