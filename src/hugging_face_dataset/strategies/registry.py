"""Route dataset profiles to extractors."""

from __future__ import annotations

from hugging_face_dataset.config import PipelineConfig
from hugging_face_dataset.profile import DatasetProfile
from hugging_face_dataset.progress.checkpoint import ProgressStore
from hugging_face_dataset.strategies.base import BaseExtractor
from hugging_face_dataset.strategies.parquet_embedded import ParquetEmbeddedExtractor
from hugging_face_dataset.strategies.raw_files import RawFilesExtractor
from hugging_face_dataset.strategies.tar_archive import TarArchiveExtractor
from hugging_face_dataset.strategies.url_column import UrlColumnExtractor
from hugging_face_dataset.strategies.zip_archive import ZipArchiveExtractor

REGISTRY: dict[str, type[BaseExtractor]] = {
    "parquet_embedded": ParquetEmbeddedExtractor,
    "image_list": ParquetEmbeddedExtractor,
    "url_column": UrlColumnExtractor,
    "zip_archive": ZipArchiveExtractor,
    "tar_archive": TarArchiveExtractor,
    "raw_files": RawFilesExtractor,
}


def build_extractor(
    profile: DatasetProfile,
    config: PipelineConfig,
    token: str | None,
    progress: ProgressStore,
) -> BaseExtractor:
    cls = REGISTRY.get(profile.strategy)
    if cls is None:
        raise ValueError(f"No extractor for strategy {profile.strategy!r} ({profile.repo_id})")
    return cls(profile, config, token, progress)
