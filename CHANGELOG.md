# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-16

Initial release. Built for the [Gemma 4 Good Hackathon](https://kaggle.com/competitions/gemma-4-good-hackathon)
(deadline 2026-05-18).

### Added

- `crowe-mycelium` CLI with `chat` / `run` / `info` / `models` subcommands.
- Backend client wrapping Ollama via `httpx`, with `OLLAMA_HOST` override.
- Modelfile (`modelfile/Modelfile`) producing the `crowelogic/gemma-4-mycelium-e4b`
  tag from the Gemma 4 E4B base. Bakes in the Crowe Logic cultivation system
  prompt and sampling defaults tuned for grounded mycology answers (temp
  0.4, top-p 0.9, ctx 8192).
- Registry JSON at `crowe_mycelium/registry.json` describing the model
  identity (base model, license, HF repo, Ollama tag, aliases, capabilities).
  Mirrored in `crowe-logic-foundry/config/models.extra.json` so the Crowe
  Logic Foundry CLI surfaces Gemma 4 Mycelium as a tier.
- Cultivation corpus preparation script (`scripts/prepare_corpus.py`):
  ingests Lion's Mane Commercial SOP (markdown), The Mushroom Grower
  Vol 1 + Vol 2 (XeLaTeX), and Mycelium EI Engine technical docs;
  strips LaTeX markup, splits on chapter/section headings, chunks to a
  configurable max length, emits `data/corpus.jsonl` + an instruction-
  tuned `data/instruct.jsonl` for SFT.
- LoRA fine-tune notebook (`scripts/finetune_lora.py`): QLoRA on Gemma 4
  E4B targeting Kaggle's free P100 tier (3 epochs, r=16, bf16 compute);
  ships an adapter to `crowelogic/gemma-4-mycelium-e4b-lora` on HF.

### Phase 1 / Phase 2 framing

- **Phase 1** (this release): Gemma 4 E4B base + Crowe Logic system-prompt
  overlay via Modelfile. No weight modification. Ships as the canonical
  `crowelogic/gemma-4-mycelium-e4b` Ollama tag for cultivation queries.
- **Phase 2** (LoRA training in progress): adapter fine-tune on the
  commercial cultivation corpus. Will replace the system-prompt-only
  Modelfile with a merged GGUF when training completes.

### Acknowledgements

Built on **Gemma** by Google DeepMind. Submission to the Gemma 4 Good
Hackathon, Special Tech Track (offline / edge AI).
