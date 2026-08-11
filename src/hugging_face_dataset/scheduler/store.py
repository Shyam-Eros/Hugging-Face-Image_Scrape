"""Persistent repository status store with cross-process locking."""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from hugging_face_dataset.repos import RepoEntry, load_repos, repo_slug


class RepoStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RepoState:
    repo_id: str
    hint: str = ""
    status: str = RepoStatus.NOT_STARTED.value
    worker_id: str = ""
    strategy: str = ""
    units_done: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    retry_count: int = 0
    max_retries: int = 3
    last_error: str = ""
    started_at: str = ""
    updated_at: str = ""
    completed_at: str = ""

    @property
    def slug(self) -> str:
        return repo_slug(self.repo_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepoState:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class SchedulerStore:
    path: Path
    stale_timeout_sec: int = 600
    max_retries: int = 3
    _lock_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_suffix(".lock")
        if not self.path.exists():
            self._write({})

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _read_unlocked(self) -> dict[str, RepoState]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {k: RepoState.from_dict(v) for k, v in raw.items()}

    def _write(self, states: dict[str, RepoState]) -> None:
        payload = {k: v.to_dict() for k, v in states.items()}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _with_lock(self, fn):
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("w") as lockf:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)

    def all_states(self) -> dict[str, RepoState]:
        return self._with_lock(self._read_unlocked)

    def get(self, repo_id: str) -> RepoState | None:
        return self.all_states().get(repo_id)

    def sync_repos(self, repos_file: Path) -> int:
        """Register repos from file; return count of newly added entries."""

        def _sync() -> int:
            states = self._read_unlocked()
            added = 0
            for entry in load_repos(repos_file):
                if entry.repo_id not in states:
                    states[entry.repo_id] = RepoState(
                        repo_id=entry.repo_id,
                        hint=entry.hint,
                        max_retries=self.max_retries,
                        updated_at=self._now(),
                    )
                    added += 1
                else:
                    states[entry.repo_id].hint = entry.hint
                    states[entry.repo_id].max_retries = self.max_retries
            self._write(states)
            return added

        return self._with_lock(_sync)

    def recover_stale(self) -> list[str]:
        """Reset in-progress repos whose heartbeat expired."""

        def _recover() -> list[str]:
            states = self._read_unlocked()
            recovered: list[str] = []
            now = time.time()
            for repo_id, st in states.items():
                if st.status != RepoStatus.IN_PROGRESS.value:
                    continue
                try:
                    updated = time.mktime(time.strptime(st.updated_at, "%Y-%m-%dT%H:%M:%SZ"))
                except (ValueError, TypeError):
                    updated = 0
                if now - updated > self.stale_timeout_sec:
                    st.status = RepoStatus.NOT_STARTED.value
                    st.worker_id = ""
                    st.last_error = "recovered from stale in_progress"
                    st.updated_at = self._now()
                    recovered.append(repo_id)
            if recovered:
                self._write(states)
            return recovered

        return self._with_lock(_recover)

    def claim_next(self, worker_id: str) -> RepoEntry | None:
        """Atomically claim the next eligible repository."""

        def _claim() -> RepoEntry | None:
            states = self._read_unlocked()
            candidates: list[tuple[int, str, RepoState]] = []
            for repo_id, st in states.items():
                if st.status == RepoStatus.NOT_STARTED.value:
                    candidates.append((0, repo_id, st))
                elif st.status == RepoStatus.FAILED.value and st.retry_count < st.max_retries:
                    candidates.append((1, repo_id, st))

            if not candidates:
                return None

            candidates.sort(key=lambda x: (x[0], x[1]))
            _, repo_id, st = candidates[0]
            st.status = RepoStatus.IN_PROGRESS.value
            st.worker_id = worker_id
            st.started_at = self._now()
            st.updated_at = st.started_at
            st.last_error = ""
            self._write(states)
            return RepoEntry(repo_id=repo_id, hint=st.hint)

        return self._with_lock(_claim)

    def heartbeat(
        self,
        repo_id: str,
        worker_id: str,
        *,
        units_done: int | None = None,
        uploaded: int | None = None,
        skipped: int | None = None,
        failed: int | None = None,
        strategy: str | None = None,
    ) -> None:
        def _beat() -> None:
            states = self._read_unlocked()
            st = states.get(repo_id)
            if st is None or st.status != RepoStatus.IN_PROGRESS.value:
                return
            if st.worker_id != worker_id:
                return
            st.updated_at = self._now()
            if units_done is not None:
                st.units_done = units_done
            if uploaded is not None:
                st.uploaded = uploaded
            if skipped is not None:
                st.skipped = skipped
            if failed is not None:
                st.failed = failed
            if strategy is not None:
                st.strategy = strategy
            self._write(states)

        self._with_lock(_beat)

    def mark_completed(
        self,
        repo_id: str,
        worker_id: str,
        *,
        strategy: str = "",
        units_done: int = 0,
        uploaded: int = 0,
        skipped: int = 0,
        failed: int = 0,
    ) -> None:
        def _done() -> None:
            states = self._read_unlocked()
            st = states.get(repo_id)
            if st is None:
                return
            if st.worker_id and st.worker_id != worker_id:
                return
            st.status = RepoStatus.COMPLETED.value
            st.worker_id = ""
            st.strategy = strategy or st.strategy
            st.units_done = units_done
            st.uploaded = uploaded
            st.skipped = skipped
            st.failed = failed
            st.completed_at = self._now()
            st.updated_at = st.completed_at
            st.last_error = ""
            self._write(states)

        self._with_lock(_done)

    def mark_failed(self, repo_id: str, worker_id: str, error: str) -> None:
        def _fail() -> None:
            states = self._read_unlocked()
            st = states.get(repo_id)
            if st is None:
                return
            if st.worker_id and st.worker_id != worker_id:
                return
            st.retry_count += 1
            st.last_error = error[:2000]
            st.worker_id = ""
            st.updated_at = self._now()
            if st.retry_count >= st.max_retries:
                st.status = RepoStatus.FAILED.value
            else:
                st.status = RepoStatus.NOT_STARTED.value
            self._write(states)

        self._with_lock(_fail)

    def mark_skipped(self, repo_id: str, worker_id: str, reason: str) -> None:
        def _skip() -> None:
            states = self._read_unlocked()
            st = states.get(repo_id)
            if st is None:
                return
            st.status = RepoStatus.SKIPPED.value
            st.worker_id = ""
            st.last_error = reason[:500]
            st.completed_at = self._now()
            st.updated_at = st.completed_at
            self._write(states)

        self._with_lock(_skip)

    def summary(self) -> dict[str, int]:
        counts = {s.value: 0 for s in RepoStatus}
        for st in self.all_states().values():
            counts[st.status] = counts.get(st.status, 0) + 1
        return counts
