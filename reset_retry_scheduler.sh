#!/usr/bin/env bash
# Reset retry scheduler to match repository_retry.txt exactly (all not_started).
# Shard checkpoints in /workspace/shyam/hf-cache/progress/ are preserved.
set -euo pipefail
source "$(dirname "$0")/_project_dir.sh"
cd "$PROJECT_DIR"

SCHED="/workspace/shyam/hf-cache/scheduler/repos_retry.json"

"${PROJECT_DIR}/.venv/bin/python3" << PY
import json
from pathlib import Path
from hugging_face_dataset.repos import load_repos

sched = Path("${SCHED}")
repos = [e.repo_id for e in load_repos(Path("repository_retry.txt"))]
if not repos:
    raise SystemExit("repository_retry.txt has no repos")

now = __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime())
states = {
    repo_id: {
        "repo_id": repo_id,
        "hint": "",
        "status": "not_started",
        "worker_id": "",
        "strategy": "",
        "units_done": 0,
        "uploaded": 0,
        "skipped": 0,
        "failed": 0,
        "retry_count": 0,
        "max_retries": 3,
        "last_error": "",
        "started_at": "",
        "updated_at": now,
        "completed_at": "",
    }
    for repo_id in repos
}
sched.parent.mkdir(parents=True, exist_ok=True)
sched.write_text(json.dumps(states, indent=2))
print(f"Reset scheduler: {len(states)} repo(s) -> not_started")
PY

echo "Run: ./run_hf_scrape_retry.sh  (or ./resume_hf_scrape_retry.sh to keep existing state)"
