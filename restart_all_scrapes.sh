#!/usr/bin/env bash
# Stop all scrape tmux sessions and restart with local HF cache
set -euo pipefail
source "$(dirname "$0")/_project_dir.sh"
DIR="$PROJECT_DIR"
cd "$DIR"

for s in hf-scrape hf-scrape-2 hf-scrape-3 hf-scrape-retry hf-scrape-retry-2 hf-scrape-retry-3; do
  if tmux has-session -t "$s" 2>/dev/null; then
    echo "Stopping $s..."
    tmux kill-session -t "$s" || true
  fi
done
sleep 2

echo "Starting main batches..."
./run_hf_scrape.sh
./run_hf_scrape_2.sh
./run_hf_scrape_3.sh

echo "Starting unified failed/skipped retry..."
./run_hf_scrape_retry.sh

echo
echo "All pipelines restarted with local cache: /local-workspace/shyam/hugging-face-dataset/.hf-cache/datasets"
echo "Monitor: tmux list-sessions | grep hf-scrape"
