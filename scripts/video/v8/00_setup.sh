#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRATCH="/Volumes/Elements/swm-yt-archive-2026-05-18"

echo ">> verifying tools..."
for bin in yt-dlp ffmpeg whisper-cli jq; do
  if ! command -v "$bin" >/dev/null; then
    echo "MISSING: $bin"
    case "$bin" in
      yt-dlp)      echo "  install: pip3 install --user yt-dlp" ;;
      ffmpeg|jq)   echo "  install: brew install $bin" ;;
      whisper-cli) echo "  install: brew install whisper-cpp" ;;
    esac
    exit 1
  fi
done

echo ">> verifying deno (yt-dlp JS runtime requirement)..."
if ! command -v deno >/dev/null; then
  echo "  installing deno via brew..."
  brew install deno
fi

echo ">> verifying Elements volume mounted..."
if [[ ! -d "/Volumes/Elements" ]]; then
  echo "ERROR: /Volumes/Elements not mounted. Plug in the drive."
  exit 1
fi

echo ">> creating directories..."
mkdir -p "$SCRATCH"/{videos,transcripts}
mkdir -p "$REPO_ROOT/video/v8"/{scenes,cards}

echo ">> setup complete."
echo "   scratch: $SCRATCH"
echo "   build:   $REPO_ROOT/video/v8"
