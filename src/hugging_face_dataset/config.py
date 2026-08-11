"""Pipeline configuration defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from hugging_face_dataset.paths import (
    CACHE_DIR,
    HUB_DIR,
    PROFILE_DIR,
    PROGRESS_DIR,
    SCHEDULER_DIR,
    SCRATCH_ROOT,
)

# Package location (may differ from PROJECT_ROOT when run from install)
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class PipelineConfig:
    gcs_bucket: str = "kl-workspace"
    gcs_prefix_root: str = "Data_scraping/Images/Huggingface-datasets"
    cache_dir: Path = field(default_factory=lambda: CACHE_DIR)
    progress_dir: Path = field(default_factory=lambda: PROGRESS_DIR)
    profile_dir: Path = field(default_factory=lambda: PROFILE_DIR)
    scheduler_dir: Path = field(default_factory=lambda: SCHEDULER_DIR)
    scheduler_file: Path = field(default_factory=lambda: SCHEDULER_DIR / "repos.json")
    upload_workers: int = 64
    url_workers: int = 128
    repo_workers: int = 4
    max_retries: int = 3
    stale_timeout_sec: int = 600
    heartbeat_interval_sec: int = 30
    url_checkpoint_batch: int = 500
    prefetch_shards: int = 2
    parquet_inflight_multiplier: int = 4
    scale_workers_per_repo: bool = False
    write_sidecar: bool = False
    max_shards: int = 0
    max_images: int = 0

    def gcs_prefix_for(self, repo_slug: str) -> str:
        return f"{self.gcs_prefix_root}/{repo_slug}".strip("/")

    def cache_for(self, repo_slug: str) -> Path:
        return self.cache_dir / repo_slug

    def scheduler_path(self) -> Path:
        return self.scheduler_file


def load_env() -> None:
    env_path = _PACKAGE_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path)
        except ImportError:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    HUB_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(HUB_DIR))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(CACHE_DIR))


def get_hf_token() -> str | None:
    load_env()
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
