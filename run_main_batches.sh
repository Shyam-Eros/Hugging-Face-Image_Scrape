#!/usr/bin/env bash
# Restart main batches 1 and 2 only (not batch 3 or failed retries)
set -euo pipefail
source "$(dirname "$0")/_project_dir.sh"
cd "$PROJECT_DIR"

for s in hf-scrape hf-scrape-2; do
  tmux kill-session -t "$s" 2>/dev/null || true
done
sleep 2

bash recover_stale_scheduler.sh
bash purge_hf_cache.sh

bash run_hf_scrape.sh
bash run_hf_scrape_2.sh

echo
echo "Main batches 1 & 2 started on NVMe."
echo "  tmux attach -t hf-scrape"
echo "  tmux attach -t hf-scrape-2"
echo "  tail -f $PROJECT_DIR/logs/hf_scrape.log"
echo "  tail -f $PROJECT_DIR/logs/hf_scrape_2.log"
