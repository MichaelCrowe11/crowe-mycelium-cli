#!/usr/bin/env bash
# Ollama Hub account setup helper.
#
# Ollama Hub uses SSH-key auth (no API tokens), so account linkage requires
# a one-time web step that cannot be automated without driving a browser.
# This script does everything around that step:
#
#  1. Ensure the SSH identity exists (~/.ollama/id_ed25519).
#  2. Print the public key in copy-ready form.
#  3. Open the Ollama account page in your default browser.
#  4. Wait for you to add the key + signal back (Enter).
#  5. Retry the manifest push so the cached 9.6GB blob lands.
#
# Once the key is linked once, every future `ollama push` is fully
# non-interactive — this script becomes a one-shot setup.
#
# Usage:
#     scripts/setup_ollama_hub.sh                            # interactive setup
#     scripts/setup_ollama_hub.sh push                       # just retry push
#     OLLAMA_NAMESPACE=michaelcrowe11 ./setup_ollama_hub.sh  # override namespace

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OLLAMA_NAMESPACE="${OLLAMA_NAMESPACE:-michaelcrowe11}"
OLLAMA_TAG_NAME="${OLLAMA_TAG_NAME:-gemma-4-mycelium-e4b}"
LOCAL_TAG="crowelogic/${OLLAMA_TAG_NAME}"
HUB_TAG="${OLLAMA_NAMESPACE}/${OLLAMA_TAG_NAME}"

cmd="${1:-setup}"

ensure_identity() {
    if [[ ! -f "$HOME/.ollama/id_ed25519" ]]; then
        echo ">> generating Ollama SSH identity..."
        mkdir -p "$HOME/.ollama"
        ssh-keygen -t ed25519 -f "$HOME/.ollama/id_ed25519" -N "" \
            -C "ollama@$(hostname -s)" >/dev/null
        echo "   created $HOME/.ollama/id_ed25519"
    fi
}

print_key() {
    echo ""
    echo "Public key to paste at https://ollama.com/account (SSH Public Keys section):"
    echo ""
    echo "---8<---"
    cat "$HOME/.ollama/id_ed25519.pub"
    echo "---8<---"
    echo ""
}

push() {
    if ! ollama list 2>/dev/null | awk '{print $1}' | grep -qx "${HUB_TAG}:latest"; then
        if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "${LOCAL_TAG}:latest"; then
            echo ">> retagging ${LOCAL_TAG} -> ${HUB_TAG}..."
            ollama cp "$LOCAL_TAG" "$HUB_TAG"
        else
            echo "ERROR: neither $LOCAL_TAG nor $HUB_TAG is built locally."
            echo "       Run scripts/ship_phase1.sh build first."
            exit 1
        fi
    fi
    echo ">> pushing $HUB_TAG to Ollama Hub..."
    if ollama push "$HUB_TAG" 2>&1 | tee /tmp/ollama-push.log; then
        if grep -q "not authorized" /tmp/ollama-push.log; then
            echo ""
            echo "Manifest write failed — your SSH key isn't linked to '$OLLAMA_NAMESPACE'."
            echo "Verify https://ollama.com/$OLLAMA_NAMESPACE exists and the key from above is on the account."
            exit 1
        fi
        echo ""
        echo "Pushed. Pull from any machine with:"
        echo "    ollama pull $HUB_TAG"
    fi
}

setup() {
    ensure_identity
    print_key
    # Open the account page if a browser is available.
    if command -v open >/dev/null 2>&1; then
        echo ">> opening https://ollama.com/account in your default browser..."
        open "https://ollama.com/account" 2>/dev/null || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "https://ollama.com/account" 2>/dev/null || true
    fi
    echo ""
    echo "Steps:"
    echo "  1. Sign in (or sign up — username '$OLLAMA_NAMESPACE' if you don't have one)."
    echo "  2. SSH Public Keys section -> Add a key -> paste the line between the ---8<--- markers above."
    echo "  3. Save."
    echo ""
    read -r -p "Press ENTER once the key is added at ollama.com/account (or Ctrl-C to abort): "
    push
}

case "$cmd" in
    setup) setup ;;
    push)  push ;;
    key)   ensure_identity; print_key ;;
    *)
        echo "usage: $0 [setup|push|key]"
        exit 2
        ;;
esac
