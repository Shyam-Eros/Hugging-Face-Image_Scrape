"""Local HF cache cleanup after processing a unit."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


def cleanup_hf_download(cache_dir: Path, local_path: Path, rel_path: str) -> None:
    """Remove one completed blob from the HF cache.

    Never delete other ``*.incomplete`` files — prefetch may still be downloading
    the next shard in the same repo cache directory.
    """
    try:
        from huggingface_hub.file_download import try_to_delete_from_cache

        if local_path.exists():
            try_to_delete_from_cache(str(local_path))
    except Exception:
        if local_path.exists():
            local_path.unlink(missing_ok=True)

    snapshot = cache_dir / "hf_snapshot" / rel_path
    if snapshot.exists():
        snapshot.unlink(missing_ok=True)

    snap_root = cache_dir / "hf_snapshot"
    if snap_root.exists():
        for root, _, _ in os.walk(snap_root, topdown=False):
            p = Path(root)
            if p != snap_root and not any(p.iterdir()):
                shutil.rmtree(p, ignore_errors=True)


def purge_repo_cache(repo_cache_dir: Path) -> None:
    """Remove all downloaded blobs for one repository slug."""
    if not repo_cache_dir.exists():
        return
    try:
        shutil.rmtree(repo_cache_dir, ignore_errors=True)
        log.info("Purged repo cache: %s", repo_cache_dir)
    except Exception as exc:
        log.warning("Failed to purge %s: %s", repo_cache_dir, exc)
