#!/usr/bin/env bash
# Phase 1 ship script: Gemma 4 base + Crowe Logic system-prompt overlay,
# tagged + pushed to Ollama Hub.
#
# Idempotent. Each step skips if its output is already in place.
#
# Usage:
#     scripts/ship_phase1.sh                # full pipeline
#     scripts/ship_phase1.sh build          # local build only (no push)
#     scripts/ship_phase1.sh smoke          # smoke tests only
#     scripts/ship_phase1.sh push           # Ollama Hub push only
#
# Env overrides:
#     OLLAMA_NAMESPACE=michaelcrowe11       # your ollama.com username
#     OLLAMA_TAG_NAME=gemma-4-mycelium-e4b  # default matches the README
#     BASE_MODEL=gemma4:e4b                 # source for the Modelfile FROM
#     MODELS_DIR=/Volumes/Elements/ollama-models   # external drive target

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OLLAMA_NAMESPACE="${OLLAMA_NAMESPACE:-michaelcrowe11}"
OLLAMA_TAG_NAME="${OLLAMA_TAG_NAME:-gemma-4-mycelium-e4b}"
LOCAL_TAG="crowelogic/${OLLAMA_TAG_NAME}"
HUB_TAG="${OLLAMA_NAMESPACE}/${OLLAMA_TAG_NAME}"
BASE_MODEL="${BASE_MODEL:-gemma4:e4b}"
MODELS_DIR="${MODELS_DIR:-/Volumes/Elements/ollama-models}"

cmd="${1:-all}"

_ensure_ollama_running() {
    if ! pgrep -fq "ollama serve" 2>/dev/null; then
        echo "  starting Ollama..."
        open -a Ollama
        sleep 4
    fi
}

_ensure_external_models_dir() {
    # / on this machine is tight on space. Models live on the external drive
    # via a symlink so the system Ollama.app finds them at the default path.
    if [[ ! -L "$HOME/.ollama/models" ]]; then
        if [[ -d "$HOME/.ollama/models" ]]; then
            echo "  WARN: ~/.ollama/models is a real dir; not migrating automatically."
            echo "        Move it to $MODELS_DIR and symlink before running again."
            return 1
        fi
        mkdir -p "$MODELS_DIR"
        ln -sfn "$MODELS_DIR" "$HOME/.ollama/models"
        echo "  symlinked ~/.ollama/models -> $MODELS_DIR"
    fi
}

_ensure_ssh_identity() {
    if [[ ! -f "$HOME/.ollama/id_ed25519" ]]; then
        echo "  generating Ollama identity key..."
        mkdir -p "$HOME/.ollama"
        ssh-keygen -t ed25519 -f "$HOME/.ollama/id_ed25519" -N "" -C "ollama@$(hostname -s)" >/dev/null
    fi
    echo "  public key (paste at https://ollama.com/account if not linked):"
    sed 's/^/    /' "$HOME/.ollama/id_ed25519.pub"
}

pull_base() {
    _ensure_external_models_dir
    _ensure_ollama_running
    if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$BASE_MODEL"; then
        echo "  $BASE_MODEL already present"
        return 0
    fi
    echo "  pulling $BASE_MODEL (this is the 9.6GB step)..."
    ollama pull "$BASE_MODEL"
}

build() {
    _ensure_ollama_running
    if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "${LOCAL_TAG}:latest"; then
        echo "  $LOCAL_TAG already built"
        return 0
    fi
    echo "  building $LOCAL_TAG from modelfile/Modelfile..."
    ollama create "$LOCAL_TAG" -f modelfile/Modelfile
}

smoke() {
    _ensure_ollama_running
    echo "  identity probe..."
    local reply
    reply="$(ollama run "$LOCAL_TAG" "What are you?" 2>/dev/null | tail -5)"
    if echo "$reply" | grep -qiE "gemma 4 mycelium|crowe logic|cultivation"; then
        echo "  identity: OK"
    else
        echo "  identity: UNEXPECTED — got: $reply"
    fi
    echo "  cultivation probe..."
    reply="$(ollama run "$LOCAL_TAG" "My agar plate has a small pink patch. What's happening?" 2>/dev/null | tail -10)"
    if echo "$reply" | grep -qiE "contamination|species|inoculat|culture"; then
        echo "  cultivation: OK (responds with cultivation domain language)"
    else
        echo "  cultivation: UNEXPECTED — got: $reply"
    fi
}

push() {
    _ensure_ollama_running
    _ensure_ssh_identity
    if ! ollama list 2>/dev/null | awk '{print $1}' | grep -qx "${HUB_TAG}:latest"; then
        echo "  retagging ${LOCAL_TAG} -> ${HUB_TAG}..."
        ollama cp "$LOCAL_TAG" "$HUB_TAG"
    fi
    echo "  pushing $HUB_TAG to Ollama Hub..."
    echo "  (if this fails with 'not authorized to push to this namespace',"
    echo "   add the public key above at https://ollama.com/account, then re-run.)"
    ollama push "$HUB_TAG"
}

all() {
    echo ">> pull_base"; pull_base
    echo ">> build";     build
    echo ">> smoke";     smoke
    echo ">> push";      push
    echo ""
    echo "Phase 1 shipped. Pull from any machine with:"
    echo "    ollama pull $HUB_TAG"
}

case "$cmd" in
    all)    all ;;
    pull)   pull_base ;;
    build)  build ;;
    smoke)  smoke ;;
    push)   push ;;
    keys)   _ensure_ssh_identity ;;
    *)
        echo "usage: $0 [all|pull|build|smoke|push|keys]"
        exit 2
        ;;
esac
