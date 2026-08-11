#!/usr/bin/env python3
"""
Download jackyhate/text-to-image-2M (Text-to-Image Dataset Collection) → GCS.

Dataset: https://huggingface.co/datasets/jackyhate/text-to-image-2M
  - Curated ~2M text-image pairs (WebDataset tar shards, ~500+ GB total)
  - data_512_2M: 46 tar shards; data_1024_10K: 1 tar shard

GCS: gs://kl-workspace/Data_scraping/Images/Huggingface-datasets/text-to-image-2M/

Usage:
  python download_text-to-image-2M.py --mode metadata --dry-run
  python download_text-to-image-2M.py --mode data_512
  python download_text-to-image-2M.py --mode all
"""

from hf_gcs_mirror import run_mirror

REPO_ID = "jackyhate/text-to-image-2M"
GCS_PREFIX = "Data_scraping/Images/Huggingface-datasets/text-to-image-2M"

MODE_PATTERNS = {
    "metadata": ["README.md"],
    "data_512": ["README.md", "data_512_2M/**"],
    "data_1024": ["README.md", "data_1024_10K/**"],
    "all": ["**"],
}

if __name__ == "__main__":
    raise SystemExit(
        run_mirror(
            repo_id=REPO_ID,
            gcs_prefix_default=GCS_PREFIX,
            mode_patterns=MODE_PATTERNS,
            mode_choices=list(MODE_PATTERNS),
            default_mode="all",
            epilog=__doc__,
        )
    )
