"""Automatic Hugging Face dataset inspection."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download, list_repo_files

from hugging_face_dataset.profile import DatasetProfile
from hugging_face_dataset.repos import RepoEntry

IMAGE_COLUMN_NAMES = ("jpg", "image", "images", "img", "picture", "photo")
URL_COLUMN_NAMES = (
    "url",
    "image_url",
    "image path",
    "image_path",
    "imagepath",
    "link",
    "source_url",
    "original_url",
    "download_url",
)


def _is_embedded_image(value) -> bool:
    if isinstance(value, dict) and isinstance(value.get("bytes"), (bytes, bytearray)):
        return len(value["bytes"]) > 100
    if isinstance(value, (bytes, bytearray)) and len(value) > 100:
        return True
    return False


def _is_url(value) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _classify_row(row: dict) -> tuple[str, list[str], list[str]]:
    embedded, urls, lists = [], [], []
    for key, val in row.items():
        kl = key.lower()
        if _is_embedded_image(val):
            embedded.append(key)
        elif _is_url(val):
            urls.append(key)
        elif isinstance(val, list) and val and (_is_url(val[0]) or _is_embedded_image(val[0])):
            lists.append(key)
        elif kl in IMAGE_COLUMN_NAMES and _is_embedded_image(val):
            embedded.append(key)
        elif kl in URL_COLUMN_NAMES and _is_url(val):
            urls.append(key)
    if embedded:
        return "parquet_embedded", embedded, []
    if urls:
        return "url_column", [], urls
    if lists:
        return "image_list", lists, []
    return "unknown", [], []


def inspect_repo(entry: RepoEntry, token: str | None, cache_dir: Path) -> DatasetProfile:
    repo_id = entry.repo_id
    hint = entry.hint

    if hint in ("url", "urls"):
        return DatasetProfile(
            repo_id=repo_id,
            strategy="url_column",
            url_columns=["url"],
            confidence=0.9,
            notes=f"hint={hint}",
        )
    if "image list" in hint or "images list" in hint:
        return DatasetProfile(
            repo_id=repo_id,
            strategy="image_list",
            image_columns=["images"],
            confidence=0.9,
            notes=f"hint={hint}",
        )

    files = list_repo_files(repo_id, repo_type="dataset", token=token)
    files = [f for f in files if not f.startswith(".git")]

    parquets = [f for f in files if f.endswith(".parquet")]
    csvs = [f for f in files if f.endswith(".csv")]
    zips = [f for f in files if f.endswith(".zip")]
    images = [f for f in files if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]

    cache_dir.mkdir(parents=True, exist_ok=True)

    if parquets:
        sample = parquets[0]
        local = Path(
            hf_hub_download(
                repo_id=repo_id,
                filename=sample,
                repo_type="dataset",
                cache_dir=str(cache_dir),
                token=token,
            )
        )
        pf = pq.ParquetFile(local)
        table = pf.read_row_group(0)
        row = {name: table.column(name)[0].as_py() for name in table.column_names}
        strategy, img_cols, url_cols = _classify_row(row)
        if strategy == "unknown":
            for name in table.column_names:
                if name.lower() in IMAGE_COLUMN_NAMES:
                    img_cols = [name]
                    strategy = "parquet_embedded"
                    break
        local.unlink(missing_ok=True)
        return DatasetProfile(
            repo_id=repo_id,
            strategy=strategy if strategy != "unknown" else "parquet_embedded",
            image_columns=img_cols or ["jpg", "image"],
            url_columns=url_cols,
            file_glob="**/*.parquet",
            confidence=0.85,
            notes=f"sample={sample}, cols={list(table.column_names)[:10]}",
        )

    if csvs:
        sample = csvs[0]
        local = Path(
            hf_hub_download(
                repo_id=repo_id,
                filename=sample,
                repo_type="dataset",
                cache_dir=str(cache_dir),
                token=token,
            )
        )
        with local.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            row = next(reader, {})
        local.unlink(missing_ok=True)
        strategy, img_cols, url_cols = _classify_row(row)
        if not url_cols:
            for k in row:
                if k.lower() in URL_COLUMN_NAMES or "path" in k.lower():
                    url_cols = [k]
                    strategy = "url_column"
                    break
        return DatasetProfile(
            repo_id=repo_id,
            strategy=strategy if strategy != "unknown" else "url_column",
            url_columns=url_cols or ["url"],
            file_glob="**/*.csv",
            confidence=0.75,
            notes=f"sample={sample}",
        )

    if zips:
        raw = next((z for z in zips if "raw" in z.lower()), zips[0])
        return DatasetProfile(
            repo_id=repo_id,
            strategy="zip_archive",
            zip_filename=raw,
            confidence=0.8,
            notes=f"zip={raw}",
        )

    tars = [f for f in files if f.lower().endswith((".tar.gz", ".tgz", ".tar"))]
    if tars:
        raw = next((t for t in tars if "raw" in t.lower() or "image" in t.lower()), tars[0])
        return DatasetProfile(
            repo_id=repo_id,
            strategy="tar_archive",
            zip_filename=raw,
            confidence=0.8,
            notes=f"tar={raw}",
        )

    if images:
        return DatasetProfile(
            repo_id=repo_id,
            strategy="raw_files",
            file_glob="**/*.{png,jpg,jpeg,webp}",
            confidence=0.7,
            notes=f"{len(images)} image files on HF",
        )

    return DatasetProfile(
        repo_id=repo_id,
        strategy="unknown",
        confidence=0.0,
        notes="Could not detect image storage; inspect manually",
    )
