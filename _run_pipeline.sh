#!/usr/bin/env bash
# Shared tmux launcher for pipeline schedule.
# Usage: source _run_pipeline.sh && run_pipeline_schedule SESSION REPOS_FILE SCHEDULER_JSON [extra args]
set -euo pipefail

run_pipeline_schedule() {
  local SESSION="$1"
  local REPOS_FILE="$2"
  local SCHED="$3"
  shift 3

  source "$(dirname "${BASH_SOURCE[0]}")/_project_dir.sh"
  local DIR="$PROJECT_DIR"
  local LOG_DIR="${DIR}/logs"
  local LOG_NAME="${SESSION#hf-scrape-}"
  [[ "$LOG_NAME" == "$SESSION" ]] && LOG_NAME="scrape"

  source "$DIR/_hf_cache_env.sh"
  mkdir -p "$LOG_DIR"
  cd "$DIR"

  if [[ -x "${DIR}/.venv/bin/pipeline" ]]; then
    PIPELINE=( "${DIR}/.venv/bin/pipeline" )
  else
    uv sync -q
    PIPELINE=( uv run pipeline )
  fi

  local SCALE_FLAG=""
  if [[ "${PIPELINE_SCALE_WORKERS:-0}" == "1" ]]; then
    SCALE_FLAG="--scale-workers-per-repo"
  fi

  local EXTRA=("$@")
  local CMD="${PIPELINE[*]} schedule --repos ${REPOS_FILE} --scheduler-file \"${SCHED}\" \
    --repo-workers ${REPO_WORKERS} --upload-workers ${UPLOAD_WORKERS} --url-workers ${URL_WORKERS} \
    --prefetch-shards ${PREFETCH_SHARDS} ${SCALE_FLAG} --max-retries 5 --stale-timeout 600 \
    ${EXTRA[*]} 2>&1 | tee -a \"${LOG_DIR}/hf_${LOG_NAME}.log\"; echo DONE_hf_${LOG_NAME}_exit=\$?; bash"

  for s in "$SESSION"; do
    tmux kill-session -t "$s" 2>/dev/null || true
  done
  pkill -f "pipeline schedule --repos ${REPOS_FILE}" 2>/dev/null || true
  sleep 2

  tmux new-session -d -s "$SESSION" -n scrape "$CMD"

  echo "Started tmux session: $SESSION"
  echo "  Repos:    ${REPOS_FILE}"
  echo "  Workers:  repos=${REPO_WORKERS} upload=${UPLOAD_WORKERS} url=${URL_WORKERS} prefetch=${PREFETCH_SHARDS}"
  echo "  State:    ${SCHED}"
  echo "  Log:      tail -f ${LOG_DIR}/hf_${LOG_NAME}.log"
  echo "  Attach:   tmux attach -t ${SESSION}"
}
