#!/usr/bin/env bash
# Extract per-act source-footage clips from the Michael Crowe QA interview.
#
# The 22-min interview has Michael speaking head-on at the camera, locked down,
# good lighting — the exact shape sync.so wants for lip-sync. We pull a clip per
# act roughly matching the act's audio duration (+1s headroom on each end).
#
# Why arbitrary timestamps: sync.so re-animates the mouth to match the NEW
# audio. The original speech content is discarded; we only need (a) Michael's
# face on camera, (b) continuous footage without cuts, (c) duration ≥ target.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC=~/Projects/southwest-mushrooms/marketing/teasers/interview-michael-crowe-qa.mp4
OUT="${REPO_ROOT}/video/source"

if [[ ! -f "$SRC" ]]; then
    echo "ERROR: source missing: $SRC"
    exit 1
fi

mkdir -p "$OUT"

# Spread across the interview for visual variety. Each duration is rounded up
# from the audio target (act1=9.7s → 12s clip, etc.) — sync.so trims if needed.
# Format: act,start_seconds,duration_seconds
clips=(
    "1,30,12"      # 0:30 - 0:42  (Act 1: 9.74s audio)
    "2,180,18"     # 3:00 - 3:18  (Act 2: 15.88s audio)
    "4,420,20"     # 7:00 - 7:20  (Act 4: 17.03s audio)
    "5,720,16"     # 12:00 - 12:16 (Act 5: 13.22s audio)
)

for spec in "${clips[@]}"; do
    IFS=',' read -r act start dur <<< "$spec"
    out="${OUT}/act${act}.mp4"
    if [[ -f "$out" ]]; then
        echo "  act${act}: exists, skip"
        continue
    fi
    echo "  act${act}: extracting ${dur}s from ${start}s..."
    # -c copy is fast but doesn't allow precise seeking on non-keyframes;
    # re-encode at high bitrate to get frame-accurate cuts. Output H.264 + AAC
    # at the source 1280x720 res so sync.so sees a clean MP4.
    ffmpeg -y -loglevel error \
        -ss "$start" -i "$SRC" -t "$dur" \
        -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k \
        -movflags +faststart \
        "$out"
    dur_actual=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$out")
    printf "    wrote $(basename $out)  %.2fs\n" "$dur_actual"
done

echo ""
echo "Source clips ready in ${OUT}/"
ls -la "$OUT/"
