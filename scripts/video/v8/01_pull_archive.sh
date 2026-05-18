#!/usr/bin/env bash
set -euo pipefail

SCRATCH="/Volumes/Elements/swm-yt-archive-2026-05-18"
CHANNEL="${SWM_YT_CHANNEL:-https://www.youtube.com/@SouthwestMushrooms/videos}"
N="${SWM_YT_N:-30}"

echo ">> pulling top $N videos from $CHANNEL"
echo "   into $SCRATCH/videos"

# 1080p mp4, embed metadata, write info JSON, cap at N videos.
# --download-archive prevents re-downloads on re-run.
yt-dlp \
  --format "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best" \
  --merge-output-format mp4 \
  --write-info-json \
  --write-auto-subs \
  --sub-lang en \
  --convert-subs srt \
  --download-archive "$SCRATCH/archive.txt" \
  --playlist-end "$N" \
  --output "$SCRATCH/videos/%(upload_date)s_%(title).100B_%(id)s.%(ext)s" \
  --no-overwrites \
  "$CHANNEL"

echo ""
echo ">> pulled. inventory:"
ls -la "$SCRATCH/videos" | head -20
echo "   total mp4 files: $(find "$SCRATCH/videos" -name '*.mp4' 2>/dev/null | wc -l)"
echo "   total srt files: $(find "$SCRATCH/videos" -name '*.srt' 2>/dev/null | wc -l)"
