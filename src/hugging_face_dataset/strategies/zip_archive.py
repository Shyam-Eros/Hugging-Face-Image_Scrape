"""Extract images from ZIP archives on Hugging Face."""

from __future__ import annotations

import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.cloud import storage
from huggingface_hub import list_repo_files
from tqdm import tqdm

from hugging_face_dataset.cache_cleanup import cleanup_hf_download, purge_repo_cache
from hugging_face_dataset.hf_download import download_hf_file
from hugging_face_dataset.config import PipelineConfig
from hugging_face_dataset.profile import DatasetProfile
from hugging_face_dataset.progress.checkpoint import ProgressStore
from hugging_face_dataset.strategies.base import BaseExtractor, RunStats
from hugging_face_dataset.upload.gcs import make_storage_client, upload_file

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")


class ZipArchiveExtractor(BaseExtractor):
    def run(self, *, dry_run: bool = False) -> RunStats:
        cfg = self.config
        slug = self.profile.slug
        cache_dir = cfg.cache_for(slug)
        images_prefix = f"{cfg.gcs_prefix_for(slug)}/images"

        zip_name = self.profile.zip_filename
        if not zip_name:
            zips = [f for f in list_repo_files(self.profile.repo_id, repo_type="dataset", token=self.token) if f.endswith(".zip")]
            zip_name = next((z for z in zips if "raw" in z.lower()), zips[0] if zips else "")

        if not zip_name:
            print("  No zip file found")
            return RunStats()

        unit_id = f"zip:{zip_name}"
        if self.progress.is_done(unit_id):
            print(f"  Skip completed zip: {zip_name}")
            return RunStats()

        if dry_run:
            print(f"  would extract: {zip_name}")
            return RunStats()

        local_zip = download_hf_file(
            repo_id=self.profile.repo_id,
            filename=zip_name,
            cache_dir=cache_dir,
            token=self.token,
        )

        client = make_storage_client(cfg.upload_workers)
        stats = RunStats()
        extract_root = cache_dir / "extract" / Path(zip_name).stem
        if extract_root.exists():
            shutil.rmtree(extract_root)
        extract_root.mkdir(parents=True)

        try:
            with zipfile.ZipFile(local_zip) as zf:
                img_names = [
                    n
                    for n in zf.namelist()
                    if n.lower().endswith(IMAGE_SUFFIXES)
                    and not n.startswith("__")
                    and not Path(n).name.startswith(".")
                ]
                zf.extractall(extract_root, members=img_names)

            image_files = sorted(
                p
                for p in extract_root.rglob("*")
                if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and not p.name.startswith(".")
            )

            def upload_one(path: Path) -> str:
                ext = path.suffix.lower()
                stem = path.stem
                upload_file(client, path, cfg.gcs_bucket, f"{images_prefix}/{stem}{ext}")
                return "uploaded"

            with ThreadPoolExecutor(max_workers=cfg.upload_workers) as pool:
                futures = {pool.submit(upload_one, p): p for p in image_files}
                for fut in tqdm(as_completed(futures), total=len(futures), desc="ZIP → GCS", unit="img"):
                    if fut.result() == "uploaded":
                        stats.uploaded += 1
                    else:
                        stats.failed += 1
        finally:
            shutil.rmtree(extract_root, ignore_errors=True)
            purge_repo_cache(cache_dir)

        self.progress.mark_done(unit_id, uploaded=stats.uploaded, skipped=stats.skipped, failed=stats.failed)
        cleanup_hf_download(cache_dir, local_zip, zip_name)
        return stats
