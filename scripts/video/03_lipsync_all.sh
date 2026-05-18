#!/usr/bin/env bash
# Submit all 4 act lip-sync jobs to sync.so in parallel.
#
# Each job: (source-footage clip, ElevenLabs narration MP3) → sync.so re-
# animates Michael's mouth to match the new audio. Server-side processing
# takes ~5-10 min per clip; we run all 4 concurrently.
#
# Output: video/synced/act{1,2,4,5}.mp4
#
# Prerequisites:
# - scripts/video/01_generate_audio.py  (produced video/audio/act*.mp3)
# - scripts/video/02_extract_source_clips.sh  (produced video/source/act*.mp4)
# - SYNC_API_KEY in ~/.env.secrets
# - gcloud authed to a principal with read access to crowe-lipsync-staging

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNNER=~/Projects/crowe-logic-ai/scripts/swm-cut/sync-direct/run.py
AUDIO_DIR="${REPO_ROOT}/video/audio"
SOURCE_DIR="${REPO_ROOT}/video/source"
SYNCED_DIR="${REPO_ROOT}/video/synced"
LOG_DIR="${REPO_ROOT}/video/logs"
MODEL="${SYNC_MODEL:-sync-3}"

mkdir -p "$SYNCED_DIR" "$LOG_DIR"

if [[ ! -x "$RUNNER" ]] && [[ ! -f "$RUNNER" ]]; then
    echo "ERROR: sync.so runner missing: $RUNNER"
    exit 1
fi

# Convert MP3 → WAV so the file extension matches what sync.so expects on the
# GCS signed URL. WAV is also more lip-sync friendly (no compressed-audio
# decoding artefacts feeding into the phoneme detector).
echo "=== convert MP3 → WAV ==="
for act in 1 2 4 5; do
    mp3="${AUDIO_DIR}/act${act}.mp3"
    wav="${AUDIO_DIR}/act${act}.wav"
    if [[ -f "$wav" ]]; then
        echo "  act${act}: WAV exists, skip"
        continue
    fi
    ffmpeg -y -loglevel error -i "$mp3" -acodec pcm_s16le -ar 44100 -ac 2 "$wav"
    echo "  act${act}: $(basename $wav) written"
done

echo ""
echo "=== submit 4 jobs in parallel ==="
declare -a pids=()
for act in 1 2 4 5; do
    video="${SOURCE_DIR}/act${act}.mp4"
    audio="${AUDIO_DIR}/act${act}.wav"
    out="${SYNCED_DIR}/act${act}.mp4"
    log="${LOG_DIR}/lipsync_act${act}.log"

    if [[ -f "$out" ]]; then
        echo "  act${act}: synced output exists ($out), skip"
        continue
    fi

    if [[ ! -f "$video" ]] || [[ ! -f "$audio" ]]; then
        echo "  act${act}: input missing (video=$video audio=$audio), skip"
        continue
    fi

    echo "  act${act}: submitting (prefix=gemma4myc-act${act})..."
    nohup python3 "$RUNNER" \
        "$video" "$audio" "$out" \
        --model "$MODEL" \
        --name-prefix "gemma4myc-act${act}" \
        > "$log" 2>&1 &
    pids+=($!)
    echo "    PID $!, log $log"
done

if [[ ${#pids[@]} -eq 0 ]]; then
    echo "  all outputs already exist; nothing to submit"
    exit 0
fi

echo ""
echo "=== waiting on ${#pids[@]} job(s) ==="
fail=0
for pid in "${pids[@]}"; do
    if wait "$pid"; then
        echo "  PID $pid completed"
    else
        echo "  PID $pid FAILED (exit $?)"
        fail=$((fail + 1))
    fi
done

echo ""
echo "=== results ==="
for act in 1 2 4 5; do
    out="${SYNCED_DIR}/act${act}.mp4"
    if [[ -f "$out" ]]; then
        dur=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$out" 2>/dev/null)
        size=$(stat -f '%z' "$out")
        printf "  ✓ act%d: %5.1fs  %s\n" "$act" "$dur" "$(numfmt --to=iec $size 2>/dev/null || echo "$size B")"
    else
        log="${LOG_DIR}/lipsync_act${act}.log"
        echo "  ✗ act${act}: failed; tail of $log:"
        tail -5 "$log" 2>/dev/null | sed 's/^/      /'
    fi
done

exit $fail
