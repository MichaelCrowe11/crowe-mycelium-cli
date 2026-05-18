#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=v9
mkdir -p "$OUT/segs"

VF="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"

# Each segment: <name> <input> <inpoint> <duration>
# Act 3 (65s) now uses freshly-rendered CLI animation (36s of `--help` / `info` /
# `models` / typing a real question) followed by grower b-roll (29s) - no
# fabricated model output. Original screencap had wrong responses.
SEGS=(
  "01_sora_desert       sora/06-desert-lab-sunrise.mp4   0     8"
  "02_cli_anim_intro    v9/cli_anim.mp4                  0     8"
  "03_real_act1         source/act1.mp4                  0     9"
  "04_facility_tour     source/act2.mp4                  0     15.5"
  "05_cli_anim_main     v9/cli_anim.mp4                  0     36"
  "06_lab_work_mid      source/act4.mp4                  0     12"
  "07_sora_datacenter   sora/03-datacenter-cold.mp4      0     8"
  "08_facility_close    source/act2.mp4                  10    9"
  "09_lab_work_long     source/act4.mp4                  2     18.1"
  "10_outro_real        source/act5.mp4                  0     13.9"
)

# Generate each segment normalized
> "$OUT/segs/concat.txt"
for row in "${SEGS[@]}"; do
  set -- $row
  name=$1; src=$2; ss=$3; t=$4
  outfile="$OUT/segs/${name}.mp4"
  ffmpeg -hide_banner -loglevel error -y \
    -ss "$ss" -t "$t" -i "$src" \
    -an -vf "$VF" \
    -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p \
    -movflags +faststart \
    "$outfile"
  echo "file '$(pwd)/$outfile'" >> "$OUT/segs/concat.txt"
  printf "  built %-20s %ss\n" "$name" "$t"
done

# Concat to silent video
ffmpeg -hide_banner -loglevel error -y \
  -f concat -safe 0 -i "$OUT/segs/concat.txt" \
  -c:v copy -an \
  "$OUT/video_silent.mp4"
echo "concat done -> $OUT/video_silent.mp4"

# Voice-only stem (audio_mix.m4a had the old Cosmic music baked in - two beds fight)
VOICE="v8/voice.wav"
# Engine's Reply instrumental
MUSIC="/Volumes/Elements/Substrate_Final_Release_Instrumental/AlbumMasters/mp3_320/08 - The Engine's Reply - Album Master.mp3"

# Get total video duration
VIDEO_DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT/video_silent.mp4")
echo "video dur: ${VIDEO_DUR}s"

# Final mix: voice at full volume, music ducked to -22dB under voice with 2.5s fade in/out
# Music: pull middle of track (skip intro buildup), trim to video length, fade in/out
MUSIC_START=20  # skip first 20s of music intro
ffmpeg -hide_banner -loglevel error -y \
  -i "$OUT/video_silent.mp4" \
  -i "$VOICE" \
  -ss "$MUSIC_START" -t "$VIDEO_DUR" -i "$MUSIC" \
  -filter_complex "\
    [1:a]volume=1.0[voice]; \
    [2:a]volume=0.18,afade=t=in:st=0:d=2.5,afade=t=out:st=$(echo "$VIDEO_DUR - 3" | bc):d=3[bed]; \
    [voice][bed]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[aout]" \
  -map 0:v -map "[aout]" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 \
  -shortest -movflags +faststart \
  "$OUT/film_v9.mp4"

echo "DONE -> $OUT/film_v9.mp4"
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT/film_v9.mp4"
