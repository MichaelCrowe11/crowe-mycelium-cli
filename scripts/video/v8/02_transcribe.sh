#!/usr/bin/env bash
# Build SRT transcripts for every pulled mp4. Prefers YouTube auto-subs
# when present; falls back to whisper-cli for anything missing.
set -euo pipefail

SCRATCH="/Volumes/Elements/swm-yt-archive-2026-05-18"
MODEL="${WHISPER_MODEL:-base.en}"
MODEL_DIR="${WHISPER_MODEL_DIR:-$HOME/.cache/whisper-cpp}"

mkdir -p "$MODEL_DIR" "$SCRATCH/transcripts"
MODEL_PATH="$MODEL_DIR/ggml-$MODEL.bin"

if [[ ! -f "$MODEL_PATH" ]]; then
  echo ">> downloading ggml-$MODEL.bin..."
  curl -L --fail -o "$MODEL_PATH" \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$MODEL.bin"
fi

cd "$SCRATCH/videos"
shopt -s nullglob

# Pass 1: copy any YouTube auto-subs into transcripts dir
for srt in *.en.srt; do
  [[ -f "$srt" ]] || continue
  base="${srt%.en.srt}"
  target="$SCRATCH/transcripts/${base}.srt"
  if [[ ! -f "$target" ]]; then
    cp "$srt" "$target"
    echo "   copied auto-subs: ${base:0:60}..."
  fi
done

# Pass 2: whisper-cli for any mp4 lacking an SRT
for vid in *.mp4; do
  [[ -f "$vid" ]] || continue
  base="${vid%.mp4}"
  target="$SCRATCH/transcripts/${base}.srt"
  if [[ -f "$target" ]]; then
    continue
  fi

  echo ">> whisper transcribing: ${base:0:60}..."
  tmp_wav="$SCRATCH/tmp_$$.wav"
  ffmpeg -y -loglevel error -i "$vid" -ac 1 -ar 16000 -vn "$tmp_wav"
  # whisper-cli emits a sibling .srt named after the input wav stem
  whisper-cli \
    --model "$MODEL_PATH" \
    --output-srt \
    --threads 8 \
    "$tmp_wav" \
    > /dev/null
  if [[ -f "${tmp_wav}.srt" ]]; then
    mv "${tmp_wav}.srt" "$target"
  fi
  rm -f "$tmp_wav"
done

echo ""
echo ">> transcripts:"
ls "$SCRATCH/transcripts/" | wc -l
echo "   in $SCRATCH/transcripts/"
