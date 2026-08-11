#!/usr/bin/env bash
# Parallel HF image scheduler → GCS (repository.txt)
set -euo pipefail

SESSION="hf-scrape"
source "$(dirname "$0")/_project_dir.sh"
DIR="$PROJECT_DIR"
LOG_DIR="${DIR}/logs"
SCHED="/workspace/shyam/hf-cache/scheduler/repos.json"
source "$DIR/_hf_cache_env.sh"
source "$DIR/_pipeline_workers.sh"
mkdir -p "$LOG_DIR"
cd "$DIR"

uv sync -q

SCALE_FLAG=""
if [[ "${PIPELINE_SCALE_WORKERS}" == "1" ]]; then
  SCALE_FLAG="--scale-workers-per-repo"
fi

CMD="uv run pipeline schedule --repos repository.txt --scheduler-file \"$SCHED\" --repo-workers ${REPO_WORKERS} --upload-workers ${UPLOAD_WORKERS} --url-workers ${URL_WORKERS} --prefetch-shards ${PREFETCH_SHARDS} ${SCALE_FLAG} --stale-timeout 300 2>&1 | tee -a \"$LOG_DIR/hf_scrape.log\"; echo DONE_hf_scrape_exit=\$?; bash"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Stopping existing $SESSION session..."
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  sleep 2
fi

tmux new-session -d -s "$SESSION" -n scrape "$CMD"

echo "Started tmux session: $SESSION"
echo "  Repos:    repository.txt"
echo "  State:    $SCHED"
echo "Attach: tmux attach -t $SESSION"
echo "Log:    tail -f $LOG_DIR/hf_scrape.log"
