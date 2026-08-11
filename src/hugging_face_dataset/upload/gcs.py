"""GCS upload helpers."""

from __future__ import annotations

import io
from pathlib import Path

from google.cloud import storage
from PIL import Image
from requests.adapters import HTTPAdapter

FORMAT_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def make_storage_client(pool_size: int = 64) -> storage.Client:
    """Create a GCS client whose HTTP pool matches concurrent upload workers."""
    pool_size = max(10, pool_size)
    client = storage.Client()
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
    if client._http is not None:
        client._http.mount("https://", adapter)
        auth_request = getattr(client._http, "_auth_request", None)
        if auth_request is not None:
            session = getattr(auth_request, "session", None)
            if session is not None:
                session.mount("https://", adapter)
    return client


def upload_bytes(
    client: storage.Client,
    data: bytes,
    bucket: str,
    blob_path: str,
    content_type: str,
) -> None:
    client.bucket(bucket).blob(blob_path).upload_from_string(data, content_type=content_type)


def upload_file(
    client: storage.Client,
    local_path: Path,
    bucket: str,
    blob_path: str,
) -> None:
    client.bucket(bucket).blob(blob_path).upload_from_filename(str(local_path))


def extract_image_bytes(img_val, image_column: str) -> tuple[bytes, str, str] | None:
    """Return (data, ext, content_type) or None."""
    if img_val is None:
        return None
    if isinstance(img_val, dict):
        raw = img_val.get("bytes")
        if isinstance(raw, (bytes, bytearray)) and len(raw) >= 4:
            raw = bytes(raw)
            if raw[:4] == b"\x89PNG":
                return raw, ".png", "image/png"
            if raw[:3] == b"\xff\xd8\xff":
                return raw, ".jpg", "image/jpeg"
            if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
                return raw, ".webp", "image/webp"
    if isinstance(img_val, (bytes, bytearray)) and len(img_val) >= 4:
        return extract_image_bytes({"bytes": bytes(img_val)}, image_column)
    return None


def encode_image_fallback(img_val) -> tuple[bytes, str, str]:
    if isinstance(img_val, dict):
        raw = img_val.get("bytes") or img_val.get("path")
        if isinstance(raw, (bytes, bytearray)):
            img = Image.open(io.BytesIO(raw))
        elif isinstance(raw, str):
            img = Image.open(raw)
        else:
            raise TypeError(f"Unexpected image dict: {list(img_val.keys())}")
    elif isinstance(img_val, (bytes, bytearray)):
        img = Image.open(io.BytesIO(img_val))
    else:
        raise TypeError(type(img_val).__name__)
    fmt = (img.format or "JPEG").upper()
    ext = FORMAT_EXT.get(fmt, ".jpg")
    buf = io.BytesIO()
    save_fmt = "JPEG" if ext == ".jpg" else ext.lstrip(".").upper()
    img.convert("RGB").save(buf, format=save_fmt, quality=95)
    return buf.getvalue(), ext, CONTENT_TYPE.get(ext, "application/octet-stream")
