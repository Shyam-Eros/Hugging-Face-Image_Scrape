#!/usr/bin/env python3
"""
Download qidouxiong619/dreamlip_long_captions → GCS.

Dataset: https://huggingface.co/datasets/qidouxiong619/dreamlip_long_captions
  - CC3M / CC12M / YFCC15M caption CSVs with image URLs (~55 GB total)
  - No hosted images on HF

GCS: gs://kl-workspace/Data_scraping/Images/Huggingface-datasets/dreamlip_long_captions/

Usage:
  python download_dreamlip_long_captions.py --mode cc3m
  python download_dreamlip_long_captions.py --mode all
"""

from hf_gcs_mirror import run_mirror

REPO_ID = "qidouxiong619/dreamlip_long_captions"
GCS_PREFIX = "Data_scraping/Images/Huggingface-datasets/dreamlip_long_captions"

MODE_PATTERNS = {
    "metadata": ["README.md"],
    "cc3m": ["README.md", "cc3m_*.csv"],
    "cc12m": ["README.md", "cc12m_*.csv"],
    "yfcc15m": ["README.md", "yfcc15m_*.csv"],
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
