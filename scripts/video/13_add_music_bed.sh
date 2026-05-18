#!/usr/bin/env bash
# Add Substrate "The Mycelium Network" as background music bed under the
# narration. Music is duck-compressed via sidechain against the narration so
# spoken word stays intelligible.
#
# Mix levels:
#   narration: 0 dB (full)
#   music:    -16 dB nominal, sidechain-ducked another ~8 dB when narration is present
#   fade in:   1.5 s
#   fade out:  2.5 s
#
# Input:  video/final/film_v5_real.mp4  (assembled by 12_recut_real_footage.sh)
# Output: video/final/film_v6_scored.mp4

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IN="${REPO_ROOT}/video/final/film_v5_real.mp4"
OUT="${REPO_ROOT}/video/final/film_v6_scored.mp4"
MUSIC="/Volumes/Elements/08 The Mycelium Network.mp3"

if [[ ! -f "$IN" ]]; then
    echo "abort: missing $IN — run 12_recut_real_footage.sh first"
    exit 1
fi
if [[ ! -f "$MUSIC" ]]; then
    echo "abort: missing music track $MUSIC"
    exit 1
fi

DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$IN")
FADE_OUT_START=$(awk "BEGIN{printf \"%.3f\", $DUR - 2.5}")

echo "  film duration: ${DUR}s"
echo "  fade-out begins: ${FADE_OUT_START}s"
echo "  music: $(basename "$MUSIC")"

# Filter graph:
#   - Extract narration audio (a0) and the music track (a1)
#   - Trim music to film duration, fade in/out
#   - asplit narration into two: one for the final mix (a0_main) and one
#     for the sidechain key (a0_key)
#   - sidechaincompress music against narration key — music ducks when
#     narration energy crosses threshold
#   - amix narration + ducked music → final stereo
ffmpeg -y -loglevel error \
    -i "$IN" \
    -stream_loop -1 -i "$MUSIC" \
    -filter_complex "
        [0:a]asplit=2[a0_main][a0_key];
        [1:a]atrim=0:${DUR},asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo,volume=-16dB,afade=t=in:st=0:d=1.5,afade=t=out:st=${FADE_OUT_START}:d=2.5[music];
        [music][a0_key]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=400:makeup=1[music_d];
        [a0_main][music_d]amix=inputs=2:duration=first:weights='1.0 0.85':normalize=0[a]
    " \
    -map 0:v -map "[a]" \
    -c:v copy \
    -c:a aac -b:a 192k -movflags +faststart \
    "$OUT"

echo ""
echo "=== result ==="
ls -lh "$OUT"
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT"
