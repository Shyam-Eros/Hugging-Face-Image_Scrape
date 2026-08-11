"""Extract embedded images from parquet shards with concurrent GCS uploads."""

from __future__ import annotations

import hashlib
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from pathlib import Path

import pyarrow.parquet as pq
from google.cloud import storage
from huggingface_hub import list_repo_files
from tqdm import tqdm

from hugging_face_dataset.cache_cleanup import cleanup_hf_download
from hugging_face_dataset.hf_download import download_hf_file
from hugging_face_dataset.strategies.base import BaseExtractor, RunStats
from hugging_face_dataset.upload.gcs import encode_image_fallback, extract_image_bytes, make_storage_client, upload_bytes


def iter_parquet_rows(parquet_path: Path):
    pf = pq.ParquetFile(parquet_path)
    for rg_idx in range(pf.num_row_groups):
        table = pf.read_row_group(rg_idx)
        columns = {name: table.column(name) for name in table.column_names}
        for row_idx in range(table.num_rows):
            yield row_idx, {name: columns[name][row_idx].as_py() for name in columns}


def row_image_id(row: dict, row_index: int, image_column: str, id_columns: list[str]) -> str:
    for field in id_columns:
        val = row.get(field)
        if val is not None and str(val).strip():
            return str(val).strip().replace("/", "_")
    for field in ("url", "source_url", "original_url"):
        val = row.get(field)
        if val is not None and str(val).strip():
            return hashlib.sha256(str(val).encode("utf-8")).hexdigest()
    img_val = row.get(image_column)
    parsed = extract_image_bytes(img_val, image_column)
    if parsed:
        return hashlib.sha256(parsed[0]).hexdigest()
    return f"row_{row_index:08d}"


class ParquetEmbeddedExtractor(BaseExtractor):
    def run(self, *, dry_run: bool = False) -> RunStats:
        cfg = self.config
        slug = self.profile.slug
        cache_dir = cfg.cache_for(slug)
        gcs_prefix = cfg.gcs_prefix_for(slug)
        images_root = f"{gcs_prefix}/images"
        image_col = self.profile.image_columns[0]

        files = sorted(
            f for f in list_repo_files(self.profile.repo_id, repo_type="dataset", token=self.token)
            if f.endswith(".parquet")
        )
        pending = [f for f in files if not self.progress.is_done(f)]
        if cfg.max_shards > 0:
            pending = pending[: cfg.max_shards]

        print(f"  Parquet shards: {len(files)} total, {len(pending)} remaining")

        if dry_run:
            for f in pending[:5]:
                print(f"    would process: {f}")
            return RunStats()

        workers = cfg.upload_workers
        inflight_limit = max(workers, workers * cfg.parquet_inflight_multiplier)
        client = make_storage_client(workers)
        stats = RunStats()

        def download_shard(rel_path: str) -> Path:
            return download_hf_file(
                repo_id=self.profile.repo_id,
                filename=rel_path,
                cache_dir=cache_dir,
                token=self.token,
            )

        prefetch_pool = ThreadPoolExecutor(max_workers=max(1, cfg.prefetch_shards))
        scheduled: dict[str, object] = {}

        def schedule_download(rel_path: str) -> None:
            if rel_path not in scheduled:
                scheduled[rel_path] = prefetch_pool.submit(download_shard, rel_path)

        try:
            for idx, rel_path in enumerate(tqdm(pending, desc=f"{slug} shards", unit="shard")):
                schedule_download(rel_path)
                for ahead in range(1, cfg.prefetch_shards):
                    next_idx = idx + ahead
                    if next_idx < len(pending):
                        schedule_download(pending[next_idx])

                local_path = scheduled.pop(rel_path).result()

                split = Path(rel_path).parent.as_posix() if "/" in rel_path else ""
                images_prefix = f"{images_root}/{split}".strip("/") if split else images_root

                shard_stats = {"uploaded": 0, "skipped": 0, "failed": 0}

                def process_one(item: tuple[int, dict]) -> str:
                    row_idx, row = item
                    img_val = row.get(image_col)
                    items: list = img_val if isinstance(img_val, list) else [img_val]

                    outcomes: list[str] = []
                    for i, one in enumerate(items):
                        suffix = f"_{i}" if len(items) > 1 else ""
                        image_id = row_image_id(row, row_idx, image_col, self.profile.id_columns) + suffix
                        parsed = extract_image_bytes(one, image_col)
                        if parsed:
                            data, ext, ctype = parsed
                        else:
                            try:
                                data, ext, ctype = encode_image_fallback(one)
                            except Exception:
                                outcomes.append("failed")
                                continue
                        blob = f"{images_prefix}/{image_id}{ext}"
                        upload_bytes(client, data, cfg.gcs_bucket, blob, ctype)
                        outcomes.append("uploaded")
                    if "uploaded" in outcomes:
                        return "uploaded"
                    return "failed"

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures: set = set()
                    for item in iter_parquet_rows(local_path):
                        if cfg.max_images > 0 and stats.uploaded + shard_stats["uploaded"] >= cfg.max_images:
                            break
                        futures.add(pool.submit(process_one, item))
                        if len(futures) >= inflight_limit:
                            done, futures = wait(futures, return_when=FIRST_COMPLETED)
                            for fut in done:
                                outcome = fut.result()
                                shard_stats[outcome] = shard_stats.get(outcome, 0) + 1

                    for fut in as_completed(futures):
                        outcome = fut.result()
                        shard_stats[outcome] = shard_stats.get(outcome, 0) + 1

                stats.uploaded += shard_stats["uploaded"]
                stats.skipped += shard_stats["skipped"]
                stats.failed += shard_stats["failed"]

                self.progress.mark_done(
                    rel_path,
                    uploaded=shard_stats["uploaded"],
                    skipped=shard_stats["skipped"],
                    failed=shard_stats["failed"],
                )
                cleanup_hf_download(cache_dir, local_path, rel_path)
                tqdm.write(
                    f"  {rel_path}: +{shard_stats['uploaded']} uploaded, "
                    f"{shard_stats['failed']} failed (cache purged)"
                )

                if cfg.max_images > 0 and stats.uploaded >= cfg.max_images:
                    break
        finally:
            prefetch_pool.shutdown(wait=True)

        return stats
