"""Fetch image URLs from CSV/JSONL columns with batched checkpointing."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from google.cloud import storage
from huggingface_hub import HfFileSystem, list_repo_files
from tqdm import tqdm

from hugging_face_dataset.config import PipelineConfig
from hugging_face_dataset.profile import DatasetProfile
from hugging_face_dataset.progress.checkpoint import ProgressStore
from hugging_face_dataset.strategies.base import BaseExtractor, RunStats
from hugging_face_dataset.upload.gcs import make_storage_client, upload_bytes

USER_AGENT = "hugging-face-dataset-pipeline/1.0"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def url_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def fetch_url(url: str, retries: int = 3) -> tuple[bytes, str] | None:
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries):
        try:
            with requests.get(url, headers=headers, timeout=30, stream=True) as resp:
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.content
                if len(data) < 100:
                    return None
                ctype = resp.headers.get("Content-Type", "image/jpeg")
                return data, ctype
        except Exception:
            time.sleep(min(2**attempt, 8))
    return None


def ext_from_url(url: str, ctype: str) -> str:
    path = url.split("?")[0].lower()
    for ext in IMAGE_EXTS:
        if path.endswith(ext):
            return ext
    return ".jpg"


class UrlColumnExtractor(BaseExtractor):
    def run(self, *, dry_run: bool = False) -> RunStats:
        cfg = self.config
        slug = self.profile.slug
        images_prefix = f"{cfg.gcs_prefix_for(slug)}/images"
        url_col = self.profile.url_columns[0] if self.profile.url_columns else "url"
        batch_size = cfg.url_checkpoint_batch

        files = sorted(
            f
            for f in list_repo_files(self.profile.repo_id, repo_type="dataset", token=self.token)
            if f.endswith((".csv", ".jsonl"))
        )
        pending = [f for f in files if not self.progress.is_done(f)]

        print(f"  URL files: {len(files)} total, {len(pending)} remaining")

        if dry_run:
            for f in pending[:5]:
                print(f"    would process: {f}")
            return RunStats()

        client = make_storage_client(self.config.url_workers)
        stats = RunStats()

        for rel_path in tqdm(pending, desc=f"{slug} url files", unit="file"):
            file_stats = self._process_file(
                rel_path,
                url_col,
                client,
                images_prefix,
                batch_size,
            )
            stats.uploaded += file_stats.uploaded
            stats.skipped += file_stats.skipped
            stats.failed += file_stats.failed
            self.progress.mark_done(
                rel_path,
                uploaded=file_stats.uploaded,
                skipped=file_stats.skipped,
                failed=file_stats.failed,
            )

        return stats

    def _process_file(
        self,
        rel_path: str,
        url_col: str,
        client: storage.Client,
        images_prefix: str,
        batch_size: int,
    ) -> RunStats:
        stats = RunStats()
        checkpoint_buffer: list[tuple[str, str]] = []

        def flush_checkpoint() -> None:
            if checkpoint_buffer:
                self.progress.mark_batch(checkpoint_buffer)
                checkpoint_buffer.clear()

        def handle(url: str) -> tuple[str, str]:
            uid = url_id(url)
            if self.progress.is_url_done(uid):
                return uid, "skipped"
            result = fetch_url(url)
            if not result:
                return uid, "failed"
            data, ctype = result
            ext = ext_from_url(url, ctype)
            upload_bytes(client, data, self.config.gcs_bucket, f"{images_prefix}/{uid}{ext}", ctype)
            return uid, "uploaded"

        urls = list(self._iter_urls(rel_path, url_col))
        if self.config.max_images > 0:
            urls = urls[: self.config.max_images]

        with ThreadPoolExecutor(max_workers=self.config.url_workers) as pool:
            futures = {pool.submit(handle, url): url for url in urls}
            for fut in as_completed(futures):
                uid, outcome = fut.result()
                stats.uploaded += int(outcome == "uploaded")
                stats.skipped += int(outcome == "skipped")
                stats.failed += int(outcome == "failed")
                checkpoint_buffer.append((f"url:{uid}", outcome))
                if len(checkpoint_buffer) >= batch_size:
                    flush_checkpoint()

        flush_checkpoint()
        return stats

    def _iter_urls(self, rel_path: str, url_col: str) -> Iterator[str]:
        fs = HfFileSystem(token=self.token)
        path = f"datasets/{self.profile.repo_id}/{rel_path}"
        with fs.open(path, "rb") as raw:
            if rel_path.endswith(".csv"):
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
                for row in csv.DictReader(text):
                    url = (row.get(url_col) or row.get("Image Path") or row.get("url") or "").strip()
                    if url.startswith("http"):
                        yield url
            else:
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                for line in text:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    url = (row.get(url_col) or row.get("url") or "").strip()
                    if url.startswith("http"):
                        yield url
