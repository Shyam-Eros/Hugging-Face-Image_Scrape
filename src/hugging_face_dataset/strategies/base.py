"""Strategy base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from hugging_face_dataset.config import PipelineConfig
from hugging_face_dataset.profile import DatasetProfile
from hugging_face_dataset.progress.checkpoint import ProgressStore


@dataclass
class RunStats:
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0


class BaseExtractor(ABC):
    def __init__(
        self,
        profile: DatasetProfile,
        config: PipelineConfig,
        token: str | None,
        progress: ProgressStore,
    ):
        self.profile = profile
        self.config = config
        self.token = token
        self.progress = progress

    @abstractmethod
    def run(self, *, dry_run: bool = False) -> RunStats:
        ...
