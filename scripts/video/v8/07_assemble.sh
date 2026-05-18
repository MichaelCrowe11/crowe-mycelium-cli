#!/usr/bin/env bash
# Assemble v8: title + acts + end, with mixed VO sources and ducked music.
#
# Layout (target timing, seconds):
#   0-5     title.mp4               (no audio)
#   5-30    act1_intro.mp4          (keep original Michael audio)
#   30-44   act2_facility_open.mp4  (mute, EL act2 audio)
#   44-60   act2_facility_mid.mp4   (mute, EL act2 audio continues)
#   60-125  act3_demo.mp4           (keep terminal audio) [OPTIONAL]
#   125-155 act4_michael_close.mp4  (mute, EL act4 audio)
#   155-173 act5_vision_journey.mp4 (mute, EL act5 audio)
#   173-185 act5_vision_wide.mp4    (mute, EL act5 audio continues)
#   185-190 end.mp4                 (no audio)
#
# Music: Velvet Algorithm, ducked to ~20% under voice.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

V8="video/v8"
CARDS="$V8/cards"
SCENES="$V8/scenes"
AUDIO="video/audio"
OUT="video/final/film_v8.mp4"
mkdir -p video/final

# Whether to include the act3 demo segment
INCLUDE_ACT3="${INCLUDE_ACT3:-1}"
ACT3_PATH="$SCENES/act3_demo.mp4"

# ---------- 1. Render title and end cards to mp4 ----------
ffmpeg -y -loglevel error -loop 1 -i "$CARDS/title.png" -t 5 \
  -c:v libx264 -pix_fmt yuv420p -r 30 -vf "scale=1920:1080" \
  -an "$V8/title.mp4"

ffmpeg -y -loglevel error -loop 1 -i "$CARDS/end.png" -t 5 \
  -c:v libx264 -pix_fmt yuv420p -r 30 -vf "scale=1920:1080" \
  -an "$V8/end.mp4"

# ---------- 2. Build concat list ----------
CONCAT="$V8/concat.txt"
{
  echo "file '$(pwd)/$V8/title.mp4'"
  echo "file '$(pwd)/$SCENES/act1_intro.mp4'"
  echo "file '$(pwd)/$SCENES/act2_facility_open.mp4'"
  echo "file '$(pwd)/$SCENES/act2_facility_mid.mp4'"
  if [[ "$INCLUDE_ACT3" == "1" && -f "$ACT3_PATH" ]]; then
    echo "file '$(pwd)/$ACT3_PATH'"
  fi
  echo "file '$(pwd)/$SCENES/act4_michael_close.mp4'"
  echo "file '$(pwd)/$SCENES/act5_vision_journey.mp4'"
  echo "file '$(pwd)/$SCENES/act5_vision_wide.mp4'"
  echo "file '$(pwd)/$V8/end.mp4'"
} > "$CONCAT"

# ---------- 3. Concat video, keeping silent audio tracks where they exist ----------
# All scenes are encoded same way (1080p30 h264, aac or none), so concat demuxer works.
# Title/end have -an; act1 has audio; acts 2/4/5 are muted; act3 keeps audio.
# After concat, we will rebuild the audio track from scratch.
ffmpeg -y -loglevel error -f concat -safe 0 -i "$CONCAT" \
  -c:v copy -an \
  "$V8/concat_video.mp4"

# Get total duration of concat video
CONCAT_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$V8/concat_video.mp4")
echo ">> concat video duration: ${CONCAT_DUR}s"

# ---------- 4. Build the spoken-voice audio track ----------
# Time-positioned mix of multiple sources:
#   - Act 1 audio extracted from the original scene (real Michael)
#   - act2.mp3 (ElevenLabs)
#   - act3 audio extracted from act3_demo.mp4 (terminal sounds + Michael's voice if any)
#   - act4.mp3 (ElevenLabs)
#   - act5.mp3 (ElevenLabs)

# Extract Act 1 audio
ffmpeg -y -loglevel error -i "$SCENES/act1_intro.mp4" -vn -ac 2 -ar 48000 "$V8/act1_audio.wav"
ACT1_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$V8/act1_audio.wav")

# Extract Act 3 audio if scene exists
if [[ -f "$ACT3_PATH" ]]; then
  ffmpeg -y -loglevel error -i "$ACT3_PATH" -vn -ac 2 -ar 48000 "$V8/act3_audio.wav" 2>&1 || \
    ffmpeg -y -loglevel error -f lavfi -i anullsrc=cl=stereo:r=48000 -t 65 "$V8/act3_audio.wav"
  ACT3_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$V8/act3_audio.wav")
else
  ACT3_DUR=0
fi

# Convert ElevenLabs mp3s to wav for consistent processing
for act in 2 4 5; do
  ffmpeg -y -loglevel error -i "$AUDIO/act${act}.mp3" -ac 2 -ar 48000 "$V8/act${act}_audio.wav"
done

# Compute timing offsets (in seconds)
T_TITLE_END=5
T_ACT1_END=$(echo "$T_TITLE_END + $ACT1_DUR" | bc -l)
T_ACT2_START=$T_ACT1_END
T_ACT2_END=$(echo "$T_ACT2_START + 30" | bc -l)   # ~30s for act2 facility
T_ACT3_START=$T_ACT2_END
if [[ "$INCLUDE_ACT3" == "1" && -f "$ACT3_PATH" ]]; then
  T_ACT3_END=$(echo "$T_ACT3_START + $ACT3_DUR" | bc -l)
else
  T_ACT3_END=$T_ACT3_START
fi
T_ACT4_START=$T_ACT3_END
T_ACT4_END=$(echo "$T_ACT4_START + 30" | bc -l)
T_ACT5_START=$T_ACT4_END
T_ACT5_END=$(echo "$T_ACT5_START + 30" | bc -l)

echo ">> timing:"
echo "   title 0-${T_TITLE_END}"
echo "   act1  ${T_TITLE_END}-${T_ACT1_END}"
echo "   act2  ${T_ACT2_START}-${T_ACT2_END}"
echo "   act3  ${T_ACT3_START}-${T_ACT3_END}"
echo "   act4  ${T_ACT4_START}-${T_ACT4_END}"
echo "   act5  ${T_ACT5_START}-${T_ACT5_END}"

# Build the voice track with adelay-placed sources mixed together.
# adelay takes ms.
to_ms() { echo "$1 * 1000" | bc -l | cut -d. -f1; }

D_ACT1=$(to_ms "$T_TITLE_END")
D_ACT2=$(to_ms "$T_ACT2_START")
D_ACT3=$(to_ms "$T_ACT3_START")
D_ACT4=$(to_ms "$T_ACT4_START")
D_ACT5=$(to_ms "$T_ACT5_START")

# Build voice mix
ACT3_INPUT=""
ACT3_FILTER=""
ACT3_MAP_LABEL=""
if [[ "$INCLUDE_ACT3" == "1" && -f "$V8/act3_audio.wav" ]]; then
  ACT3_INPUT="-i $V8/act3_audio.wav"
  # input index depends on order; we add act3 as 3rd input after act1, act2
  # for simplicity, count below
  :
fi

# Use a single ffmpeg invocation with all voice inputs
INPUTS=(
  "-i" "$V8/act1_audio.wav"
  "-i" "$V8/act2_audio.wav"
)
NEXT_IDX=2
ACT3_LABEL=""
if [[ "$INCLUDE_ACT3" == "1" && -f "$V8/act3_audio.wav" ]]; then
  INPUTS+=("-i" "$V8/act3_audio.wav")
  ACT3_LABEL="[${NEXT_IDX}:a]adelay=${D_ACT3}|${D_ACT3}[a3];"
  NEXT_IDX=$((NEXT_IDX+1))
fi
INPUTS+=("-i" "$V8/act4_audio.wav")
ACT4_IDX=$NEXT_IDX
NEXT_IDX=$((NEXT_IDX+1))
INPUTS+=("-i" "$V8/act5_audio.wav")
ACT5_IDX=$NEXT_IDX

FILTER="[0:a]adelay=${D_ACT1}|${D_ACT1}[a1];"
FILTER+="[1:a]adelay=${D_ACT2}|${D_ACT2}[a2];"
FILTER+="${ACT3_LABEL}"
FILTER+="[${ACT4_IDX}:a]adelay=${D_ACT4}|${D_ACT4}[a4];"
FILTER+="[${ACT5_IDX}:a]adelay=${D_ACT5}|${D_ACT5}[a5];"

if [[ -n "$ACT3_LABEL" ]]; then
  FILTER+="[a1][a2][a3][a4][a5]amix=inputs=5:normalize=0:duration=longest[mixed];"
else
  FILTER+="[a1][a2][a4][a5]amix=inputs=4:normalize=0:duration=longest[mixed];"
fi
# Pad voice track to full concat video duration so -shortest in the final
# mux doesn't truncate the video.
FILTER+="[mixed]apad=whole_dur=${CONCAT_DUR}[voice]"

ffmpeg -y -loglevel error "${INPUTS[@]}" -filter_complex "$FILTER" -map "[voice]" \
  -c:a pcm_s16le -ar 48000 -ac 2 "$V8/voice.wav"

# ---------- 5. Build music bed (looped, ducked, with intro/outro fade) ----------
# Load Velvet Algorithm, trim to concat duration, fade in/out, lower volume.
ffmpeg -y -loglevel error -stream_loop -1 -i "$V8/music.mp3" -t "$CONCAT_DUR" \
  -af "volume=0.22,afade=t=in:st=0:d=1.5,afade=t=out:st=$(echo "$CONCAT_DUR - 1.5" | bc -l):d=1.5" \
  -c:a pcm_s16le -ar 48000 -ac 2 "$V8/music_bed.wav"

# ---------- 6. Sidechain duck music under voice ----------
ffmpeg -y -loglevel error \
  -i "$V8/voice.wav" \
  -i "$V8/music_bed.wav" \
  -filter_complex "[1:a][0:a]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[ducked];[0:a][ducked]amix=inputs=2:normalize=0[final]" \
  -map "[final]" -c:a aac -b:a 192k -ar 48000 -ac 2 "$V8/audio_mix.m4a"

# ---------- 7. Mux audio with concat video + burn subtitles if present ----------
if [[ -f "$V8/subtitles.srt" ]]; then
  ffmpeg -y -loglevel error \
    -i "$V8/concat_video.mp4" \
    -i "$V8/audio_mix.m4a" \
    -filter_complex "[0:v]subtitles=$V8/subtitles.srt:force_style='Fontsize=22,Outline=1,Shadow=0,Alignment=2,MarginV=60'[vout]" \
    -map "[vout]" -map "1:a" \
    -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p \
    -c:a copy \
    -movflags +faststart \
    -shortest \
    "$OUT"
else
  ffmpeg -y -loglevel error \
    -i "$V8/concat_video.mp4" \
    -i "$V8/audio_mix.m4a" \
    -c:v copy \
    -c:a copy \
    -movflags +faststart \
    -shortest \
    "$OUT"
fi

echo ""
echo ">> wrote $OUT"
ffprobe -v error -show_entries format=duration,size,bit_rate \
  -show_entries stream=width,height,r_frame_rate "$OUT"
