"""Track uploaded image IDs without re-listing GCS every shard."""

from __future__ import annotations

from google.cloud import storage

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


class ExistingIndex:
    """Load GCS prefix once per repo; update in memory as uploads complete."""

    def __init__(self, client: storage.Client, bucket: str, prefix: str):
        self._ids: set[str] = set()
        blob_prefix = f"{prefix.rstrip('/')}/"
        for blob in client.list_blobs(bucket, prefix=blob_prefix):
            name = blob.name.rsplit("/", 1)[-1]
            for ext in IMAGE_EXTS:
                if name.endswith(ext):
                    self._ids.add(name[: -len(ext)])
                    break

    def __contains__(self, image_id: str) -> bool:
        return image_id in self._ids

    def add(self, image_id: str) -> None:
        self._ids.add(image_id)

    def __len__(self) -> int:
        return len(self._ids)
