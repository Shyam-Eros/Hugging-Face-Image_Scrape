#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_project_dir.sh"
cd "$PROJECT_DIR"

echo "══════════════════════════════════════════════════════════════"
echo "  Tier 1 New Data Scrape — $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "══════════════════════════════════════════════════════════════"

echo
echo "▶ Host load (shared VM)"
uptime | sed 's/^/  /'
free -h | grep Mem | sed 's/^/  /'

echo
echo "▶ Process"
pgrep -af 'pipeline schedule.*repository_new_data_tier1' 2>/dev/null | grep -v pgrep | sed 's/^/  /' || echo "  (not running)"

echo
echo "▶ Scheduler"
.venv/bin/pipeline status --scheduler-only \
  --repos repository_new_data_tier1.txt \
  --scheduler-file /workspace/shyam/hf-cache/scheduler/repos_new_data_tier1.json 2>/dev/null | sed 's/^/  /'

echo
echo "▶ Checkpoint totals"
.venv/bin/python3 << 'PY'
import csv, json, re
from pathlib import Path
from hugging_face_dataset.repos import repo_slug

def parse_size(s):
    s = (s or '').strip().upper()
    if not s: return None
    m = re.match(r'^([\d.]+)\s*([KMB])?$', s.replace(',', ''))
    if not m: return None
    n, u = float(m.group(1)), m.group(2) or ''
    return int(n * {'K': 1e3, 'M': 1e6, 'B': 1e9}.get(u, 1))

sizes = {r['dataset']: parse_size(r['size']) for r in csv.DictReader(open('new_data.csv'))}
prog = Path('/workspace/shyam/hf-cache/progress')
total = 0
for line in open('repository_new_data_tier1.txt'):
    repo = line.strip()
    if not repo or repo.startswith('#'):
        continue
    slug = repo_slug(repo)
    pf = prog / f'{slug}.jsonl'
    up = units = 0
    if pf.exists():
        for row in pf.read_text().splitlines():
            if not row.strip():
                continue
            rec = json.loads(row)
            if rec.get('status') == 'done':
                units += 1
                up += rec.get('uploaded', 0)
    total += up
    tgt = sizes.get(repo)
    pct = f"{100 * up / tgt:.1f}%" if tgt else "?"
    print(f"  {repo}: {up:,} uploaded ({pct}) [{units} units]")
print(f"\n  Tier 1 total uploaded: {total:,}")
PY

echo
echo "▶ Log tail"
if [[ -f logs/hf_new-data.log ]]; then
  tr '\r' '\n' < logs/hf_new-data.log | grep -E '\[w[0-9]|=== |completed |ERROR |shards:|URL files:' | tail -10 | sed 's/^/  /'
fi

echo
echo "Attach: tmux attach -t hf-scrape-new-data"
echo "Log:    tail -f logs/hf_new-data.log"
