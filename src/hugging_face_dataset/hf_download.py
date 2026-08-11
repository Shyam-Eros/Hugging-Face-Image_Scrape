"""Thread-safe Hugging Face Hub downloads with retries."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from huggingface_hub import hf_hub_download

log = logging.getLogger(__name__)

_CACHE_LOCKS: dict[str, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()

_RETRYABLE = (FileNotFoundError, OSError)


def _cache_lock(cache_dir: Path) -> threading.Lock:
    key = str(cache_dir.resolve())
    with _CACHE_LOCKS_GUARD:
        if key not in _CACHE_LOCKS:
            _CACHE_LOCKS[key] = threading.Lock()
        return _CACHE_LOCKS[key]


def download_hf_file(
    *,
    repo_id: str,
    filename: str,
    cache_dir: Path,
    token: str | None,
    repo_type: str = "dataset",
    max_attempts: int = 5,
) -> Path:
    """Download one Hub file; serialize per cache_dir and retry transient cache races."""
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            with _cache_lock(cache_dir):
                path = hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    repo_type=repo_type,
                    cache_dir=str(cache_dir),
                    token=token,
                )
            return Path(path)
        except _RETRYABLE as exc:
            if isinstance(exc, OSError) and exc.errno not in (2,):
                raise
            last_err = exc
            delay = min(2**attempt, 30)
            log.warning(
                "HF download retry %s/%s for %s (%s): %s",
                attempt + 1,
                max_attempts,
                filename,
                repo_id,
                exc,
            )
            time.sleep(delay)
    assert last_err is not None
    raise last_err
