# Status - 2026-05-18

This repo was prepared for the **Gemma 4 Good Hackathon** (deadline 2026-05-18 23:59 UTC).
**Decision: held. Not submitted to this hackathon.**

The deliverable foundation is in place: code, Ollama image on the Hub, video
pipeline, writeup, model card. The components that would back the
submission's core claim ("offline cultivation intelligence that runs on a
single laptop") are not all ready today:

- **Phase 2 LoRA fine-tune**: blocked on upstream `mlx-lm` 0.31. Gemma 4 E4B
  multimodal attention layout (k_norm + sliding-window k_eq_v) is not yet
  implemented. Verified 2026-05-18: training launches with the text-only
  extracted base model on `/Volumes/Elements/gemma-4-e4b-text-mlx/` and fails
  with `ValueError: Received 126 parameters not in model`. Same failure on
  multiple iteration / batch / layer configurations.
- **Live Ollama runtime**: `ollama runner --ollama-engine` was hanging on
  multimodal model load on the development M4 as of 2026-05-18 12:21 PT.
  Model loaded successfully ~32h earlier; root cause not isolated.
- **Cloud training fallback (Azure ML)**: Crowe Mycology subscription
  (`4ea8ab04-9d53-46cf-9d80-de7d625ba88a`) has 0/0 GPU quota across all SKUs in
  `eastus2`. The 2026-05-13 Microsoft Foundry quota requests were for Azure
  OpenAI / Anthropic MaaS, not raw AzureML training compute.
- **Cloud training fallback (Kaggle)**: notebook scaffolding is committed, but
  a 2026-05-17 papermill run failed with `No kernel name found in notebook`.

## What IS ready (v0.1 artifacts, preserved in this repo)

- `crowe_mycelium/` - CLI package (chat / run / info / models), system prompt
- `modelfile/Modelfile` - Phase 1 system overlay applied to Gemma 4 E4B
- Published Ollama image: [`Mcrowe1210/gemma-4-mycelium-e4b`](https://ollama.com/Mcrowe1210/gemma-4-mycelium-e4b)
- `data/instruct.jsonl` (regenerated via `scripts/prepare_corpus.py`) - 2,975
  chunks / ~2.1M chars / ~3k instruction-response pairs from the cultivation
  library (Lion's Mane SOP, Mushroom Grower Vol 1 + 2)
- `scripts/finetune_lora_mlx.py`, `scripts/finetune_lora_modal.py`,
  `scripts/submit_azure_ml.py`, `notebooks/gemma_4_mycelium_lora.ipynb` -
  four training paths, each documenting its security/cost trade-offs
- `docs/SUBMISSION.md`, `docs/HF_MODEL_CARD.md`, `docs/DEMO_SCRIPT.md`,
  `docs/VIDEO_SHOTLIST.md` - writeups for the eventual submission
- `scripts/video/` - full video pipeline (audio gen, clip extraction, lipsync,
  Sora b-roll, scoring, branded cards, music bed). Reproducible from the
  cultivation corpus and licensed source footage.
- `video/v9/build.sh` + `scripts/video/v9_make_cli_anim.py` - the alternate
  cut produced 2026-05-18 (b-roll cover + generated CLI animation, no
  fabricated model output, Engine's Reply music bed)

## When to re-open this

1. `mlx-lm` upstream lands Gemma 4 E4B multimodal attention support, OR
2. A separate transformers+PEFT path on `huggingface/peft` lands Gemma 4
   k_norm / sliding-window support, OR
3. Crowe Mycology Azure GPU quota gets approved (the requests are filed but
   are for MaaS deployments, not raw compute, so this would need a separate quota
   request for an NC-family SKU)

When one of these clears, the pipeline from `data/instruct.jsonl` → trained
adapter → fused weights → GGUF → Ollama image push to
`Mcrowe1210/gemma-4-mycelium-e4b` is fully scripted and ready to run.
