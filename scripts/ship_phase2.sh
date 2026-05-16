#!/usr/bin/env bash
# Phase 2 ship script: corpus prep -> Kaggle dataset -> Kaggle notebook.
#
# Idempotent. Each step skips or re-pushes as appropriate. Re-pushing a
# Kaggle kernel uploads a new version (the prior version stays accessible).
#
# Usage:
#     scripts/ship_phase2.sh                  # full pipeline
#     scripts/ship_phase2.sh corpus           # regen corpus JSONL only
#     scripts/ship_phase2.sh dataset          # push dataset only
#     scripts/ship_phase2.sh notebook         # push notebook only
#     scripts/ship_phase2.sh status           # poll kernel run status
#     scripts/ship_phase2.sh logs             # download latest kernel logs
#
# Env overrides:
#     KAGGLE_USER=crowelogic
#     KAGGLE_DATASET_SLUG=gemma-4-mycelium-corpus
#     KAGGLE_KERNEL_SLUG=gemma-4-mycelium-lora-fine-tune
#     PYTHON=.venv/bin/python

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-.venv/bin/python}"
KAGGLE="${KAGGLE:-.venv/bin/kaggle}"
KAGGLE_USER="${KAGGLE_USER:-crowelogic}"
KAGGLE_DATASET_SLUG="${KAGGLE_DATASET_SLUG:-gemma-4-mycelium-corpus}"
KAGGLE_KERNEL_SLUG="${KAGGLE_KERNEL_SLUG:-gemma-4-mycelium-lora-fine-tune}"
KAGGLE_DATASET_REF="${KAGGLE_USER}/${KAGGLE_DATASET_SLUG}"
KAGGLE_KERNEL_REF="${KAGGLE_USER}/${KAGGLE_KERNEL_SLUG}"

cmd="${1:-all}"

_ensure_python_deps() {
    if [[ ! -x "$PYTHON" ]]; then
        echo "  bootstrapping venv..."
        python3 -m venv .venv
        PYTHON=".venv/bin/python"
        KAGGLE=".venv/bin/kaggle"
    fi
    if ! "$PYTHON" -c "import kaggle, jupytext" 2>/dev/null; then
        echo "  installing kaggle + jupytext..."
        "$PYTHON" -m pip install --quiet --upgrade kaggle jupytext
    fi
}

corpus() {
    echo "  regenerating corpus.jsonl + instruct.jsonl from source materials..."
    "$PYTHON" scripts/prepare_corpus.py
}

dataset() {
    _ensure_python_deps
    if [[ ! -f data/instruct.jsonl ]]; then
        echo "  no data/instruct.jsonl yet; running corpus prep..."
        corpus
    fi
    mkdir -p kaggle-dataset
    cp data/instruct.jsonl kaggle-dataset/
    if [[ ! -f kaggle-dataset/dataset-metadata.json ]]; then
        cat > kaggle-dataset/dataset-metadata.json <<EOF
{
  "title": "Gemma 4 Mycelium Training Corpus",
  "id": "${KAGGLE_DATASET_REF}",
  "licenses": [{"name": "other"}],
  "description": "Instruction-tuned cultivation corpus for the Gemma 4 Mycelium LoRA. Sources: Lion's Mane Commercial SOP, The Mushroom Grower Vol 1 + Vol 2, Mycelium EI Engine technical docs. Private dataset; source material is copyrighted by Crowe Logic Inc."
}
EOF
    fi
    echo "  pushing dataset $KAGGLE_DATASET_REF..."
    # First-time create vs version-update — Kaggle's CLI differentiates.
    if "$KAGGLE" datasets status "$KAGGLE_DATASET_REF" 2>/dev/null | grep -q "ready"; then
        "$KAGGLE" datasets version -p kaggle-dataset -m "auto-update from ship_phase2.sh"
    else
        "$KAGGLE" datasets create -p kaggle-dataset --dir-mode zip 2>&1 | tail -3
    fi
}

notebook() {
    _ensure_python_deps
    echo "  converting scripts/finetune_lora.py -> notebooks/gemma_4_mycelium_lora.ipynb..."
    "$PYTHON" scripts/kernelize.py scripts/finetune_lora.py notebooks/gemma_4_mycelium_lora.ipynb
    if [[ ! -f notebooks/kernel-metadata.json ]]; then
        cat > notebooks/kernel-metadata.json <<EOF
{
  "id": "${KAGGLE_KERNEL_REF}",
  "title": "Gemma 4 Mycelium — LoRA Fine-Tune",
  "code_file": "gemma_4_mycelium_lora.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_internet": "true",
  "dataset_sources": ["${KAGGLE_DATASET_REF}"],
  "competition_sources": [],
  "kernel_sources": []
}
EOF
    fi
    echo "  pushing kernel $KAGGLE_KERNEL_REF..."
    "$KAGGLE" kernels push -p notebooks/ 2>&1 | tail -3
}

status() {
    _ensure_python_deps
    echo "  kernel status:"
    "$KAGGLE" kernels status "$KAGGLE_KERNEL_REF" 2>&1 | tail -3
}

logs() {
    _ensure_python_deps
    echo "  downloading latest kernel logs..."
    "$KAGGLE" kernels output "$KAGGLE_KERNEL_REF" -p /tmp/kaggle-logs 2>&1 | tail -3
    echo ""
    echo "  last 30 lines of stderr:"
    tail -100 /tmp/kaggle-logs/"${KAGGLE_KERNEL_SLUG}".log 2>/dev/null \
        | grep -oE '"stream_name":"stderr"[^}]*"data":"[^"]*"' \
        | sed -E 's/.*"data":"([^"]*)"$/\1/' \
        | sed 's/\\n/\n/g' \
        | tail -30
}

all() {
    echo ">> corpus";   corpus
    echo ">> dataset";  dataset
    echo ">> notebook"; notebook
    echo ""
    echo "Phase 2 staged. Kaggle will auto-run the kernel on push."
    echo "Poll with:  $0 status"
    echo "Tail logs:  $0 logs"
    echo "View at:    https://www.kaggle.com/code/${KAGGLE_KERNEL_REF}"
}

case "$cmd" in
    all)      all ;;
    corpus)   corpus ;;
    dataset)  dataset ;;
    notebook) notebook ;;
    status)   status ;;
    logs)     logs ;;
    *)
        echo "usage: $0 [all|corpus|dataset|notebook|status|logs]"
        exit 2
        ;;
esac
