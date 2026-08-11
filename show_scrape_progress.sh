#!/usr/bin/env bash
# Progress for parallel HF image scheduler
set -euo pipefail
source "$(dirname "$0")/_project_dir.sh"
DIR="$PROJECT_DIR"
cd "$DIR"

echo "══════════════════════════════════════════════════════════════"
echo "  HF Image Scheduler — $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "══════════════════════════════════════════════════════════════"

echo
echo "▶ Process"
pgrep -af 'pipeline schedule|pipeline run|scrape_hf_datasets' 2>/dev/null | grep -v pgrep | sed 's/^/  /' || echo "  (not running)"

echo
echo "▶ Log tail (batch 1)"
if [[ -f logs/hf_scrape.log ]]; then
  tr '\r' '\n' < logs/hf_scrape.log | grep -E '\[w[0-9]|=== |completed |ERROR |Parquet shards:|URL files:|Scheduler:' | tail -12 | sed 's/^/  /'
fi

echo
echo "▶ Log tail (retry batch)"
if [[ -f logs/hf_scrape_retry.log ]]; then
  tr '\r' '\n' < logs/hf_scrape_retry.log | grep -E '\[w[0-9]|=== |completed |ERROR |Parquet shards:|URL files:|Scheduler:' | tail -12 | sed 's/^/  /'
else
  echo "  (no retry log)"
fi

echo
echo "▶ Unit checkpoints"
PROG=/workspace/shyam/hf-cache/progress
if [[ -d "$PROG" ]]; then
  for f in "$PROG"/*.jsonl; do
    [[ -f "$f" ]] || continue
    n=$(grep -c '"status": "done"' "$f" 2>/dev/null || echo 0)
    echo "  $(basename "$f" .jsonl): $n unit(s) done"
  done
else
  echo "  (no progress dir yet)"
fi

echo
echo "▶ Scheduler state (batch 1)"
uv run pipeline status --repos repository.txt --scheduler-only 2>/dev/null | sed 's/^/  /' || true

echo
echo "▶ Scheduler state (common-canvas batch)"
.venv/bin/pipeline status --repos repository_commoncatalog.txt --scheduler-file /workspace/shyam/hf-cache/scheduler/repos_commoncatalog.json --scheduler-only 2>/dev/null | sed 's/^/  /' || true

echo
echo "▶ Log tail (common-canvas)"
if [[ -f logs/hf_commoncatalog.log ]]; then
  tr '\r' '\n' < logs/hf_commoncatalog.log | grep -E '\[w[0-9]|=== |completed |ERROR |Parquet shards:|URL files:|Scheduler:' | tail -12 | sed 's/^/  /'
fi

echo
echo "▶ GCS image counts"
uv run python3 - << 'PY'
from google.cloud import storage
from hugging_face_dataset.repos import load_repos, repo_slug

c = storage.Client()
for entry in load_repos():
    slug = repo_slug(entry.repo_id)
    prefix = f"Data_scraping/Images/Huggingface-datasets/{slug}/images/"
    n = sum(1 for b in c.list_blobs("kl-workspace", prefix=prefix) if b.name.endswith((".jpg", ".png", ".webp")))
    if n:
        print(f"  {slug}: {n:,} images")
PY

echo
echo "Monitor: tmux attach -t hf-scrape | tail -f $DIR/logs/hf_scrape.log"
