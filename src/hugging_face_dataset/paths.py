"""Shared filesystem paths for the pipeline."""

from __future__ import annotations

from pathlib import Path

NVME_ROOT = Path("/mnt/ai-dev-team-1-disk/shyam")
PROJECT_ROOT = NVME_ROOT / "hugging-face-dataset"
SCRATCH_ROOT = NVME_ROOT / "scratch" / "hf-cache"
WORKSPACE_STATE_ROOT = Path("/workspace/shyam/hf-cache")

CACHE_DIR = SCRATCH_ROOT / "datasets"
HUB_DIR = SCRATCH_ROOT / "hub"
PROGRESS_DIR = WORKSPACE_STATE_ROOT / "progress"
PROFILE_DIR = WORKSPACE_STATE_ROOT / "profiles"
SCHEDULER_DIR = WORKSPACE_STATE_ROOT / "scheduler"

CACHE_MARKER = SCRATCH_ROOT / "CACHE_ROOT"
