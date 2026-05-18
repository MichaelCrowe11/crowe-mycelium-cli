#!/usr/bin/env bash
set -euo pipefail

SCRATCH="/Volumes/Elements/swm-yt-archive-2026-05-18"
CHANNEL="${SWM_YT_CHANNEL:-https://www.youtube.com/@SouthwestMushrooms/videos}"
N="${SWM_YT_N:-30}"

echo ">> pulling top $N videos from $CHANNEL"
echo "   into $SCRATCH/videos"

# 1080p mp4, embed metadata, write info JSON, cap at N videos.
# --download-archive prevents re-downloads on re-run.
mkdir -p /tmp/yt-dlp-temp

# Two-path strategy: keep ffmpeg merger temp on /tmp (local SSD, no quirks),
# move finished files to Elements. Avoids the "Permission denied" issue
# that hits when merger temp lands on the external drive.
yt-dlp \
  --format "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best" \
  --merge-output-format mp4 \
  --write-info-json \
  --write-auto-subs \
  --sub-lang en \
  --convert-subs srt \
  --paths "temp:/tmp/yt-dlp-temp" \
  --paths "home:$SCRATCH/videos" \
  --download-archive "$SCRATCH/archive.txt" \
  --playlist-end "$N" \
  --output "%(upload_date)s_%(title).80B_%(id)s.%(ext)s" \
  --no-overwrites \
  "$CHANNEL"

echo ""
echo ">> pulled. inventory:"
ls -la "$SCRATCH/videos" | head -20
echo "   total mp4 files: $(find "$SCRATCH/videos" -name '*.mp4' 2>/dev/null | wc -l)"
echo "   total srt files: $(find "$SCRATCH/videos" -name '*.srt' 2>/dev/null | wc -l)"
