# Single-repo mode: dedicate all CPU/IO/bandwidth to one dataset at a time.
# Best for large parquet repos (common-canvas ~6000 shards each).
# Usage: source _pipeline_workers_single.sh before run_hf_scrape_*.sh

export REPO_WORKERS="${REPO_WORKERS:-1}"
export UPLOAD_WORKERS="${UPLOAD_WORKERS:-256}"
export URL_WORKERS="${URL_WORKERS:-256}"
export PREFETCH_SHARDS="${PREFETCH_SHARDS:-8}"
export PIPELINE_SCALE_WORKERS="${PIPELINE_SCALE_WORKERS:-0}"
