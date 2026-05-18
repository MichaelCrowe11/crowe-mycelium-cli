#!/usr/bin/env bash
# v5 recut: real Southwest Mushrooms farm footage for the act-fills where
# we're showing cultivation reality (hands, fruiting, harvest), Sora CGI
# clips kept for the abstract / conceptual transitions (datacenter,
# mycelium-neural morph, desert sunrise).
#
# Sequence:
#   title card                    3s    silent
#   01-mycelium-macro    (CGI)    8s    cold open
#   act1: 2s head + 8.8s real fruiting  10.8s  audio: act1 narration
#   03-datacenter-cold   (CGI)    6s    silent transition (abstract)
#   act2: 2s head + 13.4s real harvest  15.4s  audio: act2 narration
#   act3 terminal demo            ~25.5s
#   05-mycelium-neural-morph (CGI) 6s   silent transition (abstract reveal)
#   act4: 2s head + 16s real lions mane  18.0s  audio: act4 narration
#   seq-reishi           (real)   4s    silent transition
#   act5: 2s head + 11.8s real mushrooms  13.8s  audio: act5 narration
#   06-desert-lab-sunrise (CGI)   8s    silent outro (vision)
#   outro card                    5s    silent
#
# Output: video/final/film_v5_real.mp4 (no music — music added by 13_score.sh)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYNCED="${REPO_ROOT}/video/synced"
ENHANCED="${REPO_ROOT}/video/enhanced"
SORA="${REPO_ROOT}/video/sora"
CARDS="${REPO_ROOT}/video/cards"
SCREENCAP="${REPO_ROOT}/video/screencap"
FINAL="${REPO_ROOT}/video/final"
INT="${REPO_ROOT}/video/tmp_real"
SWM="${HOME}/Projects/southwest-mushrooms/marketing/teasers"
mkdir -p "$FINAL" "$INT"

src_head() {
    local act="$1"
    if [[ -f "${ENHANCED}/act${act}.mp4" ]]; then
        echo "${ENHANCED}/act${act}.mp4"
    else
        echo "${SYNCED}/act${act}.mp4"
    fi
}

# Build a "broll roll": concatenate one or more clips, loop to fill duration.
# Args: out_file duration clip1 [clip2 ...]
broll_roll() {
    local out="$1"; shift
    local dur="$1"; shift
    local clips=("$@")
    local tmp_list="${INT}/$(basename "$out" .mp4)_list.txt"
    : > "$tmp_list"
    # Repeat the input list until likely > dur (each clip ~4-8s, 4 reps is plenty)
    for _ in 1 2 3 4 5; do
        for c in "${clips[@]}"; do
            echo "file '${c}'" >> "$tmp_list"
        done
    done
    ffmpeg -y -loglevel error \
        -f concat -safe 0 -i "$tmp_list" \
        -t "${dur}" \
        -filter_complex "[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v]" \
        -map "[v]" -an \
        -pix_fmt yuv420p -c:v libx264 -preset fast -crf 18 \
        "$out"
}

card_to_mp4() {
    local png="$1" dur="$2" out="$3"
    ffmpeg -y -loglevel error \
        -loop 1 -t "$dur" -i "$png" \
        -f lavfi -t "$dur" -i anullsrc=channel_layout=stereo:sample_rate=44100 \
        -pix_fmt yuv420p -r 25 -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k -shortest \
        "$out"
}

bumper() {
    # Single clip, trimmed/looped to dur, silent audio.
    local src="$1" dur="$2" out="$3"
    ffmpeg -y -loglevel error \
        -stream_loop -1 -i "$src" \
        -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
        -filter_complex "[0:v]trim=0:${dur},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v]" \
        -map "[v]" -map "1:a" -t "${dur}" \
        -pix_fmt yuv420p -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k -shortest \
        "$out"
}

# 2s talking head + remaining seconds of pre-built broll roll, with full narration audio.
# Audio is sourced from the ORIGINAL v3 narration mp3 (video/audio/actN.mp3),
# not from the Wav2Lip-synced video. Wav2Lip truncates audio to a quantised
# frame count, which lopped the last fraction of a second of speech in v5/v6.
act_with_roll() {
    local act="$1" broll="$2" total="$3" head_sec="$4" out="$5"
    local head_src; head_src=$(src_head "$act")
    local audio_src="${REPO_ROOT}/video/audio/act${act}.mp3"
    local fill; fill=$(awk "BEGIN{printf \"%.3f\", $total - $head_sec}")
    ffmpeg -y -loglevel error \
        -i "$head_src" \
        -i "$broll" \
        -i "$audio_src" \
        -filter_complex "
            [0:v]trim=0:${head_sec},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v0];
            [1:v]trim=0:${fill},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v1];
            [v0][v1]concat=n=2:v=1:a=0[v];
            [2:a]asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0,aformat=channel_layouts=stereo:sample_rates=44100[a]
        " \
        -map "[v]" -map "[a]" \
        -pix_fmt yuv420p -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k \
        "$out"
}

echo "=== building real-footage broll rolls ==="
# Durations match full v3 narration audio (act1=10.92s, act2=15.49s, act4=18.13s, act5=13.95s)
# minus 2s talking-head opener.
broll_roll "${INT}/roll_act1.mp4"  9.0  "${SWM}/seq-real-oyster.mp4"    "${SWM}/seq-real-lionsmane.mp4"  && echo "  roll_act1 (oyster+lionsmane)"
broll_roll "${INT}/roll_act2.mp4"  13.6 "${SWM}/seq-harvest.mp4"        "${SWM}/seq-real-oyster.mp4"  "${SWM}/seq-lionsmane.mp4"  && echo "  roll_act2 (harvest+oyster+lionsmane)"
broll_roll "${INT}/roll_act4.mp4"  16.2 "${SWM}/seq-real-lionsmane.mp4" "${SWM}/seq-mushrooms.mp4" "${SWM}/seq-real-oyster.mp4"  && echo "  roll_act4 (real lionsmane+mushrooms+oyster)"
broll_roll "${INT}/roll_act5.mp4"  12.0 "${SWM}/seq-mushrooms.mp4"      "${SWM}/seq-reishi.mp4"        "${SWM}/seq-real-oyster.mp4"  && echo "  roll_act5 (mushrooms+reishi+oyster)"

# Real-footage replacements for the four Sora slots
broll_roll "${INT}/roll_intro.mp4"        8 "${SWM}/clip-02.mp4"  "${SWM}/clip-06.mp4"                       && echo "  roll_intro (clip-02 + clip-06)"
broll_roll "${INT}/roll_trans12.mp4"      6 "${SWM}/clip-04.mp4"  "${SWM}/clip-08.mp4"  "${SWM}/clip-00.mp4" && echo "  roll_trans12 (clip-04 + clip-08 + clip-00)"
broll_roll "${INT}/roll_trans34.mp4"      6 "${SWM}/clip-05.mp4"  "${SWM}/clip-01.mp4"                       && echo "  roll_trans34 (clip-05 + clip-01)"
broll_roll "${INT}/roll_outro_broll.mp4"  8 "${SWM}/clip-06.mp4"  "${SWM}/clip-09.mp4"                       && echo "  roll_outro_broll (clip-06 + clip-09)"

echo ""
echo "=== building segments ==="
card_to_mp4   "${CARDS}/title_card.png"                3   "${INT}/01_title.mp4"      && echo "  01_title"
bumper        "${INT}/roll_intro.mp4"                  8   "${INT}/02_intro.mp4"      && echo "  02_intro (real SWM clip-02/06)"
act_with_roll 1 "${INT}/roll_act1.mp4"                11.0 2 "${INT}/03_act1.mp4"     && echo "  03_act1 (real fruiting)"
bumper        "${INT}/roll_trans12.mp4"                6   "${INT}/04_trans12.mp4"    && echo "  04_trans12 (real SWM clips)"
act_with_roll 2 "${INT}/roll_act2.mp4"                15.6 2 "${INT}/05_act2.mp4"     && echo "  05_act2 (real harvest)"

if [[ -f "${SCREENCAP}/act3.mp4" ]]; then
    ffmpeg -y -loglevel error -i "${SCREENCAP}/act3.mp4" \
        -filter_complex "[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25,format=yuv420p[v];[0:a?]aresample=44100[a]" \
        -map "[v]" -map "[a]?" -pix_fmt yuv420p -c:v libx264 -preset fast -crf 18 \
        -c:a aac -b:a 192k "${INT}/06_act3.mp4"
    echo "  06_act3 (real terminal screencap)"
else
    card_to_mp4 "${CARDS}/act3_card.png" 10 "${INT}/06_act3.mp4" && echo "  06_act3 (card placeholder)"
fi

bumper        "${INT}/roll_trans34.mp4"                6   "${INT}/07_trans34.mp4"    && echo "  07_trans34 (real SWM clip-05/01)"
act_with_roll 4 "${INT}/roll_act4.mp4"                18.2 2 "${INT}/08_act4.mp4"     && echo "  08_act4 (real lionsmane)"
bumper        "${SWM}/seq-reishi.mp4"                  4   "${INT}/09_trans45.mp4"    && echo "  09_trans45 (real reishi)"
act_with_roll 5 "${INT}/roll_act5.mp4"                14.0 2 "${INT}/10_act5.mp4"     && echo "  10_act5 (real mushrooms+reishi)"
bumper        "${INT}/roll_outro_broll.mp4"            8   "${INT}/11_outro_broll.mp4" && echo "  11_outro_broll (real SWM clip-06/09)"
card_to_mp4   "${CARDS}/outro_card.png"                5   "${INT}/12_outro.mp4"      && echo "  12_outro"

echo ""
echo "=== concat ==="
CONCAT_LIST="${INT}/concat.txt"
: > "$CONCAT_LIST"
for f in 01_title 02_intro 03_act1 04_trans12 05_act2 06_act3 07_trans34 08_act4 09_trans45 10_act5 11_outro_broll 12_outro; do
    echo "file '${INT}/${f}.mp4'" >> "$CONCAT_LIST"
done

OUT="${FINAL}/film_v5_real.mp4"
ffmpeg -y -loglevel error \
    -f concat -safe 0 -i "$CONCAT_LIST" \
    -pix_fmt yuv420p -c:v libx264 -preset slow -crf 18 \
    -c:a aac -b:a 192k -movflags +faststart \
    "$OUT"

echo ""
echo "=== result ==="
ls -lh "$OUT"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT"
