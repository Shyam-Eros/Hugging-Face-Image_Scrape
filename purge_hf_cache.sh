#!/usr/bin/env bash
# Delete HF scratch cache only when no pipeline is running.
set -euo pipefail
source "$(dirname "$0")/_project_dir.sh"

CACHE="/mnt/ai-dev-team-1-disk/shyam/scratch/hf-cache"
OLD_CACHE="${PROJECT_DIR}/.hf-cache"
LEGACY_CACHE="/local-workspace/shyam/hugging-face-dataset/.hf-cache"

if pgrep -f "pipeline schedule" >/dev/null 2>&1; then
  echo "ERROR: pipeline still running — aborting cache purge"
  pgrep -af "pipeline schedule" || true
  exit 1
fi

for d in "$CACHE/datasets" "$CACHE/hub" "$OLD_CACHE" "$LEGACY_CACHE"; do
  if [[ -e "$d" ]]; then
    echo "Removing $d ..."
    rm -rf "$d"
  fi
done

mkdir -p "$CACHE/datasets" "$CACHE/hub"
echo "active $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$CACHE/CACHE_ROOT"
df -h /mnt/ai-dev-team-1-disk / | tail -2
echo "Cache purge done."
