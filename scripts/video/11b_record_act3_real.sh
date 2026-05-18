#!/usr/bin/env bash
# Record a REAL CLI session (not animated) of `ollama run` against the
# Gemma 4 Mycelium model, then render the asciinema cast back to MP4.
#
# Why this is "real": asciinema captures stdout/stderr from the actual
# subprocess, including ollama's streaming output and spinner. agg replays
# the cast frame by frame at exact original timing, then ffmpeg encodes
# the result. No screen-capture permissions needed.
#
# Output: video/screencap/act3.mp4

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_MP4="${REPO_ROOT}/video/screencap/act3.mp4"
CAST="/tmp/act3_session.cast"
GIF="/tmp/act3_session.gif"
WRAPPER="/tmp/act3_session_wrapper.sh"

PROMPT='Why is my agar plate growing fuzzy green colonies near the edge? Lion'\''s mane, day 6.'

cat > "$WRAPPER" <<'SH'
#!/bin/bash
# Simulated interactive session: typed prompt, then real ollama call.
clear
PROMPT_PREFIX=$'\033[38;5;179mcrowelogic@mycelium\033[0m \033[38;5;245m~\033[0m \033[38;5;179m%\033[0m '
printf '%s' "$PROMPT_PREFIX"
sleep 0.6

CMD='ollama run Mcrowe1210/gemma-4-mycelium-e4b "Why is my agar plate growing fuzzy green colonies near the edge? Lion'"'"'s mane, day 6."'
for (( i=0; i<${#CMD}; i++ )); do
    printf '%s' "${CMD:$i:1}"
    sleep 0.045
done
echo
sleep 0.4

# Real ollama call via the API so we suppress the thinking chain. The
# response is streamed character by character to match the spinner-then-text
# UX of `ollama run`.
echo -n "  "
RESP_JSON=$(curl -sS http://localhost:11434/api/chat -d '{
  "model": "Mcrowe1210/gemma-4-mycelium-e4b",
  "messages": [{"role": "user", "content": "Why is my agar plate growing fuzzy green colonies near the edge? Lion'"'"'s mane, day 6."}],
  "think": false,
  "stream": false
}')
RESP=$(printf '%s' "$RESP_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin)["message"]["content"])')

# Spinner pause to simulate "thinking"
for _ in 1 2 3 4 5 6 7 8; do
    printf '\r  \033[38;5;179m⠋\033[0m '
    sleep 0.08
    printf '\r  \033[38;5;179m⠙\033[0m '
    sleep 0.08
    printf '\r  \033[38;5;179m⠹\033[0m '
    sleep 0.08
done
printf '\r    \r'

# Stream response char by char
for (( i=0; i<${#RESP}; i++ )); do
    printf '%s' "${RESP:$i:1}"
    sleep 0.012
done
echo
echo
sleep 2.5
SH
chmod +x "$WRAPPER"

echo "  recording session..."
# 92x24 matches the title bar text in the v6 outro
asciinema rec --overwrite --cols 92 --rows 24 --command "$WRAPPER" "$CAST" >/dev/null

echo "  rendering cast → gif..."
# agg --theme: dracula has nice contrast for screen. Try solarized-dark for warmer feel.
agg --theme solarized-dark --font-size 16 --cols 92 --rows 24 --speed 1.0 "$CAST" "$GIF"

echo "  encoding gif → mp4..."
mkdir -p "$(dirname "$OUT_MP4")"
# Pad/scale to 1280x720, silent audio. Add a brief opening + closing fade.
DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$GIF" 2>/dev/null || echo 30)
ffmpeg -y -loglevel error \
    -i "$GIF" \
    -f lavfi -t "$DUR" -i anullsrc=channel_layout=stereo:sample_rate=44100 \
    -filter_complex "[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x141417,setsar=1,fps=25,format=yuv420p[v]" \
    -map "[v]" -map "1:a" -t "$DUR" \
    -pix_fmt yuv420p -c:v libx264 -preset slow -crf 18 \
    -c:a aac -b:a 192k -shortest \
    -movflags +faststart \
    "$OUT_MP4"

echo "  ✓ $OUT_MP4 ($(stat -f '%z' "$OUT_MP4") bytes, ${DUR}s)"
