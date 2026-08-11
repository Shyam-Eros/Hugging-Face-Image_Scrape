"""Upload raw image files stored directly on Hugging Face."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.cloud import storage
from huggingface_hub import list_repo_files
from tqdm import tqdm

from hugging_face_dataset.cache_cleanup import cleanup_hf_download
from hugging_face_dataset.hf_download import download_hf_file
from hugging_face_dataset.config import PipelineConfig
from hugging_face_dataset.profile import DatasetProfile
from hugging_face_dataset.progress.checkpoint import ProgressStore
from hugging_face_dataset.strategies.base import BaseExtractor, RunStats
from hugging_face_dataset.upload.gcs import make_storage_client, upload_file


class RawFilesExtractor(BaseExtractor):
    def run(self, *, dry_run: bool = False) -> RunStats:
        cfg = self.config
        slug = self.profile.slug
        cache_dir = cfg.cache_for(slug)
        images_prefix = f"{cfg.gcs_prefix_for(slug)}/images"

        files = sorted(
            f
            for f in list_repo_files(self.profile.repo_id, repo_type="dataset", token=self.token)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        )
        pending = [f for f in files if not self.progress.is_done(f)]

        print(f"  Raw image files: {len(files)} total, {len(pending)} remaining")

        if dry_run:
            for f in pending[:5]:
                print(f"    would upload: {f}")
            return RunStats()

        client = make_storage_client(cfg.upload_workers)
        stats = RunStats()

        def process_one(rel_path: str) -> str:
            stem = Path(rel_path).stem
            ext = Path(rel_path).suffix.lower()
            local = download_hf_file(
                repo_id=self.profile.repo_id,
                filename=rel_path,
                cache_dir=cache_dir,
                token=self.token,
            )
            blob = f"{images_prefix}/{stem}{ext}"
            upload_file(client, local, cfg.gcs_bucket, blob)
            cleanup_hf_download(cache_dir, local, rel_path)
            return "uploaded"

        with ThreadPoolExecutor(max_workers=cfg.upload_workers) as pool:
            futures = {pool.submit(process_one, f): f for f in pending}
            for fut in tqdm(as_completed(futures), total=len(futures), desc=f"{slug} files", unit="file"):
                outcome = fut.result()
                if outcome == "uploaded":
                    stats.uploaded += 1
                    self.progress.mark_done(futures[fut], uploaded=1)

        return stats
