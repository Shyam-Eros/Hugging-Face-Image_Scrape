#!/usr/bin/env bash
# Run assigned HF dataset downloads in parallel tmux windows.
# GCS base: gs://kl-workspace/Data_scraping/Images/Huggingface-datasets/
#
# Usage:
#   bash run_assigned_datasets.sh
#   tmux attach -t hf-assigned

set -euo pipefail

SESSION="hf-assigned"
DIR="/local-workspace/shyam/hugging-face-dataset"
LOG_DIR="${DIR}/logs"
mkdir -p "$LOG_DIR"
cd "$DIR"

pip install -q -r requirements.txt requests 2>/dev/null || pip install -q -r requirements.txt

JOBS=(
  "hdvila|download_hdvila-100M.py|--mode all"
  "dreamlip|download_dreamlip_long_captions.py|--mode all"
)

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already exists. Attach: tmux attach -t $SESSION"
  exit 0
fi

first=1
for entry in "${JOBS[@]}"; do
  IFS='|' read -r name script args <<< "$entry"
  cmd="cd \"$DIR\" && python3 $script $args 2>&1 | tee \"$LOG_DIR/${name}.log\"; echo DONE_${name}_exit=\$?; bash"
  if [[ $first -eq 1 ]]; then
    tmux new-session -d -s "$SESSION" -n "$name" "$cmd"
    first=0
  else
    tmux new-window -t "$SESSION" -n "$name" "$cmd"
  fi
done

echo "Started tmux session: $SESSION"
echo "Attach:  tmux attach -t $SESSION"
echo "Logs:    $LOG_DIR/"
echo "GCS:     gs://kl-workspace/Data_scraping/Images/Huggingface-datasets/"
echo "Pipeline: gs://kl-workspace/Data_scraping/Images/Tags-dataset/ (python -m pipeline run)"
