"""Extract images from tar/tar.gz archives on Hugging Face."""

from __future__ import annotations

import shutil
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.cloud import storage
from huggingface_hub import list_repo_files
from tqdm import tqdm

from hugging_face_dataset.cache_cleanup import cleanup_hf_download, purge_repo_cache
from hugging_face_dataset.hf_download import download_hf_file
from hugging_face_dataset.strategies.base import BaseExtractor, RunStats
from hugging_face_dataset.upload.gcs import make_storage_client, upload_file

ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".tar")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _is_archive(name: str) -> bool:
    return name.lower().endswith(ARCHIVE_SUFFIXES)


def _image_ext(name: str) -> str:
    lower = name.lower()
    for ext in IMAGE_SUFFIXES:
        if lower.endswith(ext):
            return ext
    return ""


class TarArchiveExtractor(BaseExtractor):
    def run(self, *, dry_run: bool = False) -> RunStats:
        cfg = self.config
        slug = self.profile.slug
        cache_dir = cfg.cache_for(slug)
        images_prefix = f"{cfg.gcs_prefix_for(slug)}/images"

        archives = sorted(
            f for f in list_repo_files(self.profile.repo_id, repo_type="dataset", token=self.token) if _is_archive(f)
        )
        if self.profile.zip_filename and self.profile.zip_filename not in archives:
            archives.insert(0, self.profile.zip_filename)

        pending = [a for a in archives if not self.progress.is_done(f"tar:{a}")]
        print(f"  Tar archives: {len(archives)} total, {len(pending)} remaining")

        if dry_run:
            for a in pending[:5]:
                print(f"    would extract: {a}")
            return RunStats()

        stats = RunStats()
        client = make_storage_client(self.config.upload_workers)

        for rel_path in pending:
            one = self._process_one(rel_path, cache_dir, client, images_prefix)
            stats.uploaded += one.uploaded
            stats.skipped += one.skipped
            stats.failed += one.failed

        return stats

    def _process_one(
        self,
        rel_path: str,
        cache_dir: Path,
        client: storage.Client,
        images_prefix: str,
    ) -> RunStats:
        unit_id = f"tar:{rel_path}"
        local_tar = download_hf_file(
            repo_id=self.profile.repo_id,
            filename=rel_path,
            cache_dir=cache_dir,
            token=self.token,
        )

        stats = RunStats()
        mode = "r:gz" if rel_path.lower().endswith((".tar.gz", ".tgz")) else "r"
        extract_root = cache_dir / "extract" / Path(rel_path).name.replace("/", "_")
        if extract_root.exists():
            shutil.rmtree(extract_root)
        extract_root.mkdir(parents=True)

        try:
            with tarfile.open(local_tar, mode) as tf:
                members = [
                    m
                    for m in tf.getmembers()
                    if m.isfile() and _image_ext(m.name) and not Path(m.name).name.startswith(".")
                ]
                tf.extractall(extract_root, members=members)

            image_files = sorted(
                p
                for p in extract_root.rglob("*")
                if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and not p.name.startswith(".")
            )

            def upload_one(path: Path) -> str:
                ext = path.suffix.lower()
                stem = path.stem
                upload_file(
                    client,
                    path,
                    self.config.gcs_bucket,
                    f"{images_prefix}/{stem}{ext}",
                )
                return "uploaded"

            with ThreadPoolExecutor(max_workers=self.config.upload_workers) as pool:
                futures = {pool.submit(upload_one, p): p for p in image_files}
                for fut in tqdm(as_completed(futures), total=len(futures), desc=f"TAR {Path(rel_path).name}", unit="img"):
                    if fut.result() == "uploaded":
                        stats.uploaded += 1
                    else:
                        stats.failed += 1
        finally:
            shutil.rmtree(extract_root, ignore_errors=True)
            purge_repo_cache(cache_dir)

        self.progress.mark_done(unit_id, uploaded=stats.uploaded, skipped=stats.skipped, failed=stats.failed)
        cleanup_hf_download(cache_dir, local_tar, rel_path)
        return stats
