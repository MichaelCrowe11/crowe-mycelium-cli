#!/usr/bin/env bash
# Recut: minimise on-camera time. Each act narration plays in full, but
# Michael only appears for ~2s at the start of each act. The remaining audio
# duration is covered by Sora B-roll (looped to fill).
#
# Sequence:
#   01-mycelium-macro             8s   (cold open, silent)
#   act1: 2s head + 8.8s 02-loop  10.8s (audio: act1 narration)
#   03-datacenter-cold            6s   (silent transition)
#   act2: 2s head + 13.4s 04-loop 15.4s (audio: act2 narration)
#   act3 placeholder              10s  (or real screencap if present)
#   act4: 2s head + 16s 05-loop   18.0s (audio: act4 narration)
#   act5: 2s head + 11.8s 06-loop 13.8s (audio: act5 narration)
#   01-mycelium-macro outro       8s   (silent)
#
# Sources: prefers enhanced/ (GFPGAN-polished) over synced/ for talking-head.
# Output: video/final/film_v2_minimal.mp4

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYNCED="${REPO_ROOT}/video/synced"
ENHANCED="${REPO_ROOT}/video/enhanced"
SORA="${REPO_ROOT}/video/sora"
DRAFT="${REPO_ROOT}/video/draft"
SCREENCAP="${REPO_ROOT}/video/screencap"
FINAL="${REPO_ROOT}/video/final"
INT="${REPO_ROOT}/video/tmp_recut"
mkdir -p "$FINAL" "$INT"

# Per-act: source-for-head, broll-clip, total-duration, head-seconds
# (use enhanced/ if available, else synced/)
src_head() {
    local act="$1"
    if [[ -f "${ENHANCED}/act${act}.mp4" ]]; then
        echo "${ENHANCED}/act${act}.mp4"
    else
        echo "${SYNCED}/act${act}.mp4"
    fi
}

build_act() {
    local act="$1" broll="$2" total="$3" head="$4" out="$5"
    local head_src; head_src=$(src_head "$act")
    local fill=$(awk "BEGIN{printf \"%.3f\", $total - $head}")
    echo "  act${act}: head=${head}s + broll=${fill}s from $(basename "$broll") → $(basename "$out")"
    ffmpeg -y -loglevel error \
        -i "$head_src" \
        -stream_loop -1 -i "$broll" \
        -filter_complex "
            [0:v]trim=0:${head},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v0];
            [1:v]trim=0:${fill},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v1];
            [v0][v1]concat=n=2:v=1:a=0[v];
            [0:a]atrim=0:${total},aresample=async=1:first_pts=0,aformat=channel_layouts=stereo:sample_rates=44100[a]
        " \
        -map "[v]" -map "[a]" \
        -pix_fmt yuv420p -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k \
        "$out"
}

build_bumper() {
    local broll="$1" dur="$2" out="$3"
    echo "  bumper: ${dur}s from $(basename "$broll") → $(basename "$out")"
    ffmpeg -y -loglevel error \
        -i "$broll" \
        -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
        -filter_complex "
            [0:v]trim=0:${dur},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v]
        " \
        -map "[v]" -map "1:a" -t "${dur}" \
        -pix_fmt yuv420p -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k -shortest \
        "$out"
}

if [[ -f "${SCREENCAP}/act3.mp4" ]]; then
    ACT3="${SCREENCAP}/act3.mp4"
else
    ACT3="${DRAFT}/act3_placeholder.mp4"
fi

echo "=== building segments ==="
build_bumper "${SORA}/01-mycelium-macro.mp4" 8 "${INT}/seg_01_intro.mp4"
build_act 1 "${SORA}/02-fruiting-chamber.mp4" 10.8 2 "${INT}/seg_02_act1.mp4"
build_bumper "${SORA}/03-datacenter-cold.mp4" 6 "${INT}/seg_03_trans.mp4"
build_act 2 "${SORA}/04-farmer-hands-substrate.mp4" 15.4 2 "${INT}/seg_04_act2.mp4"
echo "  act3: $(basename "$ACT3")"
cp -f "$ACT3" "${INT}/seg_05_act3.mp4"
build_act 4 "${SORA}/05-mycelium-neural-morph.mp4" 18.0 2 "${INT}/seg_06_act4.mp4"
build_act 5 "${SORA}/06-desert-lab-sunrise.mp4" 13.8 2 "${INT}/seg_07_act5.mp4"
build_bumper "${SORA}/01-mycelium-macro.mp4" 8 "${INT}/seg_08_outro.mp4"

echo ""
echo "=== concat ==="
CONCAT_LIST="${INT}/concat.txt"
: > "$CONCAT_LIST"
for f in seg_01_intro seg_02_act1 seg_03_trans seg_04_act2 seg_05_act3 seg_06_act4 seg_07_act5 seg_08_outro; do
    echo "file '${INT}/${f}.mp4'" >> "$CONCAT_LIST"
done

OUT="${FINAL}/film_v2_minimal.mp4"

# Need re-encode pass to normalise segments (act3 placeholder may have
# different SAR/fps).
ffmpeg -y -loglevel error \
    -f concat -safe 0 -i "$CONCAT_LIST" \
    -filter_complex "
        [0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v];
        [0:a]aresample=44100,aformat=channel_layouts=stereo[a]
    " \
    -map "[v]" -map "[a]" \
    -pix_fmt yuv420p -c:v libx264 -preset slow -crf 18 \
    -c:a aac -b:a 192k -movflags +faststart \
    "$OUT"

echo ""
echo "=== result ==="
ls -lh "$OUT"
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT"
