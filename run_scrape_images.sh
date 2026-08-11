#!/usr/bin/env bash
# Scrape images from HD-VILA-100M (YouTube frames) and DreamLIP (URL fetch) → GCS.
#
# Usage:
#   bash run_scrape_images.sh
#   tmux attach -t hf-scrape

set -euo pipefail

SESSION="hf-scrape"
DIR="/local-workspace/shyam/hugging-face-dataset"
LOG_DIR="${DIR}/logs"
mkdir -p "$LOG_DIR"
cd "$DIR"

uv sync -q

# Image scraping only — DreamLIP URLs (HD-VILA video scraping disabled)
DREAMLIP_CMD="uv run scrape_dreamlip_images.py --split all --metadata-source hf-stream --workers 64 2>&1 | tee -a \"$LOG_DIR/dreamlip_scrape.log\"; echo DONE_dreamlip_scrape_exit=\$?; bash"

# HD-VILA: yt-dlp + ffmpeg; needs valid YouTube cookies on this machine
# Export cookies.txt from browser: yt-dlp --cookies-from-browser chrome --cookies cookies.txt ...
# Then: export YT_DLP_COOKIES=\"$DIR/cookies.txt\"
COOKIES="${YT_DLP_COOKIES:-}"
if [[ -n "$COOKIES" ]]; then
  HDVILA_CMD="python3 scrape_hdvila_images.py --metadata-source gcs --cookies \"$COOKIES\" --workers 4 2>&1 | tee -a \"$LOG_DIR/hdvila_scrape.log\"; echo DONE_hdvila_scrape_exit=\$?; bash"
else
  COOKIES_BROWSER="${YT_DLP_BROWSER:-chrome}"
  HDVILA_CMD="python3 scrape_hdvila_images.py --metadata-source gcs --cookies-from-browser \"$COOKIES_BROWSER\" --workers 4 2>&1 | tee -a \"$LOG_DIR/hdvila_scrape.log\"; echo DONE_hdvila_scrape_exit=\$?; bash"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already exists. Attach: tmux attach -t $SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" -n dreamlip "$DREAMLIP_CMD"

echo "Started tmux session: $SESSION"
echo "  dreamlip — URL scrape → gs://kl-workspace/.../dreamlip_long_captions/images/"
echo "  (HD-VILA video scraping disabled — use scrape_hdvila_images.py manually if needed)"
echo "Attach: tmux attach -t $SESSION"
echo "Logs:   $LOG_DIR/dreamlip_scrape.log  $LOG_DIR/hdvila_scrape.log"
