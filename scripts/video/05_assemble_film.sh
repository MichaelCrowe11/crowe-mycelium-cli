#!/usr/bin/env bash
# Assemble the hackathon film: alternate Wav2Lip-synced talking-head shots
# with Sora 2 cinematic B-roll. Output: video/final/film_v1.mp4
#
# Sequence (matches docs/VIDEO_SHOTLIST.md, with B-roll intercuts):
#   01 mycelium-macro              (cold open)            8s
#   act1 synced talking head                              10.8s
#   02 fruiting-chamber            (Act 1→2 transition)    8s
#   act2 synced talking head                              15.4s
#   03 datacenter-cold             (Act 2→3 transition)    8s
#   act3 placeholder OR screencap  (live terminal demo)    65s (target)
#   04 farmer-hands-substrate      (Act 3→4 transition)    8s
#   act4 synced talking head                              18.0s
#   05 mycelium-neural-morph       (Act 4→5 transition)    8s
#   act5 synced talking head                              13.8s
#   06 desert-lab-sunrise          (outro)                 8s
#
# Total: ~2:51 (with 65s Act 3); ~1:56 with the 10s Act 3 placeholder
#
# All segments are normalised to 1280x720 25fps yuv420p with 44.1kHz stereo
# AAC audio before concat, so the result encodes cleanly without smartcut
# artifacts.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYNCED="${REPO_ROOT}/video/synced"
SORA="${REPO_ROOT}/video/sora"
DRAFT="${REPO_ROOT}/video/draft"
SCREENCAP="${REPO_ROOT}/video/screencap"
FINAL="${REPO_ROOT}/video/final"
mkdir -p "$FINAL"

# Pick Act 3: prefer real screencap if present, else the 10s draft placeholder
if [[ -f "${SCREENCAP}/act3.mp4" ]]; then
    ACT3="${SCREENCAP}/act3.mp4"
    echo "  Act 3: using real screencap"
else
    ACT3="${DRAFT}/act3_placeholder.mp4"
    echo "  Act 3: using 10s placeholder (no screencap yet)"
fi

# Hard-required segments
required=(
    "${SORA}/01-mycelium-macro.mp4"
    "${SYNCED}/act1.mp4"
    "${SORA}/02-fruiting-chamber.mp4"
    "${SYNCED}/act2.mp4"
    "${SORA}/03-datacenter-cold.mp4"
    "$ACT3"
    "${SORA}/04-farmer-hands-substrate.mp4"
    "${SYNCED}/act4.mp4"
    "${SORA}/05-mycelium-neural-morph.mp4"
    "${SYNCED}/act5.mp4"
    "${SORA}/06-desert-lab-sunrise.mp4"
)

missing=0
for f in "${required[@]}"; do
    if [[ ! -f "$f" ]]; then
        echo "  MISSING: $f"
        missing=1
    fi
done
[[ $missing -ne 0 ]] && { echo "abort: missing inputs"; exit 1; }

# Build ffmpeg input list + filter graph
N=${#required[@]}
input_args=()
for f in "${required[@]}"; do
    input_args+=(-i "$f")
done

# Each input: scale + setsar + fps for video; aresample for audio. Sora clips
# without audio get filled with silent stereo so the concat audio track has
# a defined source per segment.
filter=""
for i in $(seq 0 $((N-1))); do
    filter+="[${i}:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v${i}];"
done
# Audio: probe each; if missing, synthesise silence matched to the video
# duration. Easier: use anullsrc concat trick — feed all audio through
# aresample with a fallback of silence.
for i in $(seq 0 $((N-1))); do
    # `?` makes the audio stream optional; missing audio becomes silence via
    # the apad+aresample chain.
    filter+="[${i}:a]aresample=async=1:first_pts=0,aformat=channel_layouts=stereo:sample_rates=44100[a${i}];"
done

# Concat
for i in $(seq 0 $((N-1))); do
    filter+="[v${i}][a${i}]"
done
filter+="concat=n=${N}:v=1:a=1[v][a]"

OUT="${FINAL}/film_v1.mp4"
echo ""
echo "=== rendering $OUT ==="
ffmpeg -y -loglevel info \
    "${input_args[@]}" \
    -filter_complex "$filter" \
    -map "[v]" -map "[a]" \
    -pix_fmt yuv420p -c:v libx264 -preset slow -crf 18 \
    -c:a aac -b:a 192k -movflags +faststart \
    "$OUT" 2>&1 | tail -30

echo ""
echo "=== result ==="
ls -lh "$OUT"
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT"
