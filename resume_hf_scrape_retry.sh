#!/usr/bin/env bash
# Resume retry pipeline after adding repos to repository_retry.txt.
#
# What is preserved:
#   - Scheduler state (completed / skipped / failed repos stay as-is)
#   - Shard checkpoints in /workspace/shyam/hf-cache/progress/*.jsonl
#
# What happens on restart:
#   - New repo ids in repository_retry.txt are registered automatically
#   - in_progress repos are reset so workers can reclaim them
#   - Partially scraped repos resume from their last finished shard/file
set -euo pipefail
source "$(dirname "$0")/_project_dir.sh"
cd "$PROJECT_DIR"

SCHED="/workspace/shyam/hf-cache/scheduler/repos_retry.json"

echo "▶ Stopping any running retry pipeline..."
for s in hf-scrape-retry; do
  tmux kill-session -t "$s" 2>/dev/null || true
done
pkill -f 'pipeline schedule --repos repository_retry.txt' 2>/dev/null || true
sleep 2

echo "▶ Recovering in_progress repos (checkpoints preserved)..."
"${PROJECT_DIR}/.venv/bin/python3" << PY
import json
from pathlib import Path

path = Path("${SCHED}")
if not path.exists():
    print("  No scheduler state yet — will start fresh")
    raise SystemExit(0)

data = json.loads(path.read_text())
recovered = []
for repo_id, st in data.items():
    if st.get("status") == "in_progress":
        st["status"] = "not_started"
        st["worker_id"] = ""
        st["last_error"] = "recovered before resume"
        recovered.append(repo_id)

if recovered:
    path.write_text(json.dumps(data, indent=2))
    print(f"  Reset {len(recovered)} in_progress -> not_started")
    for repo_id in recovered:
        print(f"    {repo_id}")
else:
    print("  Nothing in_progress to reset")
PY

echo "▶ Starting pipeline (new repos in repository_retry.txt will be registered)..."
exec ./run_hf_scrape_retry.sh
