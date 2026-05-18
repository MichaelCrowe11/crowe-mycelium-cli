#!/usr/bin/env bash
# Branded recut: minimise on-camera time, lead with title card, close with
# outro card, and use the Crowe Mycology Act 3 card in place of the unbranded
# placeholder. Talking-head shots inherit the GFPGAN-polished frames from
# video/enhanced/ when present, else fall back to video/synced/.
#
# Sequence:
#   title card                    3s   (silent, brand intro)
#   01-mycelium-macro             8s   (silent cold open)
#   act1: 2s head + 8.8s b-roll   10.8s (audio: act1 narration)
#   03-datacenter-cold            6s   (silent transition)
#   act2: 2s head + 13.4s b-roll  15.4s (audio: act2 narration)
#   act3 branded card             10s  (silent placeholder OR real screencap)
#   04-farmer-hands-substrate     6s   (silent transition)
#   act4: 2s head + 16s b-roll    18.0s (audio: act4 narration)
#   05-mycelium-neural-morph      6s   (silent transition)
#   act5: 2s head + 11.8s b-roll  13.8s (audio: act5 narration)
#   06-desert-lab-sunrise         8s   (silent outro)
#   outro card                    5s   (silent, attribution)
#
# Output: video/final/film_v3_branded.mp4

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYNCED="${REPO_ROOT}/video/synced"
ENHANCED="${REPO_ROOT}/video/enhanced"
SORA="${REPO_ROOT}/video/sora"
CARDS="${REPO_ROOT}/video/cards"
SCREENCAP="${REPO_ROOT}/video/screencap"
FINAL="${REPO_ROOT}/video/final"
INT="${REPO_ROOT}/video/tmp_branded"
mkdir -p "$FINAL" "$INT"

src_head() {
    local act="$1"
    if [[ -f "${ENHANCED}/act${act}.mp4" ]]; then
        echo "${ENHANCED}/act${act}.mp4"
    else
        echo "${SYNCED}/act${act}.mp4"
    fi
}

# Wrap a PNG into a silent MP4 of given duration.
card_to_mp4() {
    local png="$1" dur="$2" out="$3"
    ffmpeg -y -loglevel error \
        -loop 1 -t "$dur" -i "$png" \
        -f lavfi -t "$dur" -i anullsrc=channel_layout=stereo:sample_rate=44100 \
        -pix_fmt yuv420p -r 25 -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k -shortest \
        "$out"
}

# Silent b-roll segment of given duration (looped if shorter than dur).
bumper() {
    local src="$1" dur="$2" out="$3"
    ffmpeg -y -loglevel error \
        -stream_loop -1 -i "$src" \
        -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
        -filter_complex "[0:v]trim=0:${dur},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v]" \
        -map "[v]" -map "1:a" -t "$dur" \
        -pix_fmt yuv420p -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k -shortest \
        "$out"
}

# 2s talking head + remaining seconds of looped b-roll, with full narration audio.
act_segment() {
    local act="$1" broll="$2" total="$3" head_sec="$4" out="$5"
    local head_src; head_src=$(src_head "$act")
    local fill; fill=$(awk "BEGIN{printf \"%.3f\", $total - $head_sec}")
    ffmpeg -y -loglevel error \
        -i "$head_src" \
        -stream_loop -1 -i "$broll" \
        -filter_complex "
            [0:v]trim=0:${head_sec},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v0];
            [1:v]trim=0:${fill},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v1];
            [v0][v1]concat=n=2:v=1:a=0[v];
            [0:a]atrim=0:${total},asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0,aformat=channel_layouts=stereo:sample_rates=44100[a]
        " \
        -map "[v]" -map "[a]" \
        -pix_fmt yuv420p -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k \
        "$out"
}

echo "=== building segments ==="

card_to_mp4 "${CARDS}/title_card.png"    3  "${INT}/01_title.mp4"     && echo "  01_title.mp4"
bumper      "${SORA}/01-mycelium-macro.mp4"          8 "${INT}/02_intro.mp4"  && echo "  02_intro.mp4"
act_segment 1 "${SORA}/02-fruiting-chamber.mp4"      10.8 2 "${INT}/03_act1.mp4"  && echo "  03_act1.mp4"
bumper      "${SORA}/03-datacenter-cold.mp4"         6 "${INT}/04_trans12.mp4"   && echo "  04_trans12.mp4"
act_segment 2 "${SORA}/04-farmer-hands-substrate.mp4" 15.4 2 "${INT}/05_act2.mp4" && echo "  05_act2.mp4"

# Act 3: real screencap if present, else branded card
if [[ -f "${SCREENCAP}/act3.mp4" ]]; then
    echo "  06_act3.mp4 (real screencap)"
    ACT3_DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "${SCREENCAP}/act3.mp4")
    ffmpeg -y -loglevel error -i "${SCREENCAP}/act3.mp4" \
        -filter_complex "[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v];[0:a?]aresample=44100[a]" \
        -map "[v]" -map "[a]?" -pix_fmt yuv420p -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k "${INT}/06_act3.mp4"
else
    card_to_mp4 "${CARDS}/act3_card.png" 10 "${INT}/06_act3.mp4" && echo "  06_act3.mp4 (branded card placeholder)"
fi

bumper      "${SORA}/05-mycelium-neural-morph.mp4"   6 "${INT}/07_trans34.mp4"   && echo "  07_trans34.mp4"
act_segment 4 "${SORA}/04-farmer-hands-substrate.mp4" 18.0 2 "${INT}/08_act4.mp4" && echo "  08_act4.mp4"
bumper      "${SORA}/05-mycelium-neural-morph.mp4"   6 "${INT}/09_trans45.mp4"   && echo "  09_trans45.mp4"
act_segment 5 "${SORA}/06-desert-lab-sunrise.mp4"    13.8 2 "${INT}/10_act5.mp4"  && echo "  10_act5.mp4"
bumper      "${SORA}/06-desert-lab-sunrise.mp4"      8 "${INT}/11_outro_broll.mp4" && echo "  11_outro_broll.mp4"
card_to_mp4 "${CARDS}/outro_card.png"    5  "${INT}/12_outro.mp4"     && echo "  12_outro.mp4"

echo ""
echo "=== concat ==="
CONCAT_LIST="${INT}/concat.txt"
: > "$CONCAT_LIST"
for f in 01_title 02_intro 03_act1 04_trans12 05_act2 06_act3 07_trans34 08_act4 09_trans45 10_act5 11_outro_broll 12_outro; do
    echo "file '${INT}/${f}.mp4'" >> "$CONCAT_LIST"
done

OUT="${FINAL}/film_v3_branded.mp4"

ffmpeg -y -loglevel error \
    -f concat -safe 0 -i "$CONCAT_LIST" \
    -c copy "$OUT" 2>/dev/null || \
ffmpeg -y -loglevel error \
    -f concat -safe 0 -i "$CONCAT_LIST" \
    -pix_fmt yuv420p -c:v libx264 -preset slow -crf 18 \
    -c:a aac -b:a 192k -movflags +faststart \
    "$OUT"

echo ""
echo "=== result ==="
ls -lh "$OUT"
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT"
