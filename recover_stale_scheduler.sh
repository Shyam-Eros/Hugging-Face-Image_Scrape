#!/usr/bin/env bash
# Recover stale in_progress repos in main batch schedulers
set -euo pipefail
source "$(dirname "$0")/_project_dir.sh"
cd "$PROJECT_DIR"

uv run python3 << 'PY'
import json
from pathlib import Path

for name, path in [
    ("repos.json", Path("/workspace/shyam/hf-cache/scheduler/repos.json")),
    ("repos_2.json", Path("/workspace/shyam/hf-cache/scheduler/repos_2.json")),
]:
    if not path.exists():
        continue
    d = json.loads(path.read_text())
    recovered = []
    for repo_id, st in d.items():
        if st.get("status") == "in_progress":
            st["status"] = "not_started"
            st["worker_id"] = ""
            st["last_error"] = "recovered manually before restart"
            recovered.append(repo_id)
    if recovered:
        path.write_text(json.dumps(d, indent=2))
        print(f"{name}: reset {len(recovered)} in_progress -> not_started")
        for r in recovered:
            print(f"  {r}")
    else:
        print(f"{name}: nothing to recover")
PY
