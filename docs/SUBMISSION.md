# Gemma 4 Mycelium — Gemma 4 Good Hackathon Submission

**Track:** Special Tech Track (Offline / Edge AI)
**Team:** Crowe Logic Inc. (Michael Crowe, sole developer)
**Model:** [`crowelogic/gemma-4-mycelium-e4b`](https://ollama.com/crowelogic/gemma-4-mycelium-e4b) on Ollama Hub · [`crowelogic/gemma-4-mycelium-e4b-lora`](https://huggingface.co/crowelogic/gemma-4-mycelium-e4b-lora) on HuggingFace
**Code:** [github.com/MichaelCrowe11/crowe-mycelium-cli](https://github.com/MichaelCrowe11/crowe-mycelium-cli)

---

## The problem

Commercial mushroom growers operate in places datacenter AI can't reach. Fruiting rooms in basements, greenhouses on rural acreage, cold rooms in tunnel houses. The humidity that grows mushrooms also kills routers. Cellular coverage is intermittent. When a grower opens an agar plate and sees an unexpected color, the answer they need lives one foot from their hand — but every commercial AI assistant assumes that hand is in a city with broadband.

The cultivation-knowledge floor in this space is also distinctively bad. General-purpose models will confidently diagnose a "pink mold" as *Neurospora* when it could be a benign secondary fruit, a bacterial bloom, or a Pleurotus dikaryon doing exactly what it's supposed to. The cost of a wrong answer is a contaminated 50-block production run — thousands of dollars and weeks of recovery. The cost of "I don't know without more context" is one extra question.

## What Gemma 4 Mycelium is

A Gemma 4 E4B fine-tune for commercial and at-home mushroom cultivation, distributed as a self-contained Ollama image that runs fully offline on a single laptop.

Three things make it useful where general models aren't:

1. **It refuses to confabulate.** The system overlay enforces *"never diagnose contamination without species, inoculation source, and visual context."* Standard Gemma 4 answers any cultivation question with confident-sounding nonsense; Gemma 4 Mycelium asks the questions a senior grower would ask first.

2. **It's grounded in commercial mycology, not Wikipedia.** The LoRA training corpus is 2.1M characters from:
   - *Lion's Mane Commercial SOP* — a 175-page commercial standard operating procedure I authored (ISBN-assigned, shipped to paying customers)
   - *The Mushroom Grower Vol 1 + Vol 2* — two production books I wrote covering everything from agar work to fruiting-room HVAC
   - Mycelium EI Engine technical docs — substrate-monitoring telemetry patterns from a live cultivation OS

   No mushroom-foraging blog, no Reddit thread. Practical knowledge a working grower would trust.

3. **It runs on the laptop in the fruiting room.** Distributed as an Ollama image; one `ollama pull` and an offline grower has it. The CLI (`crowe-mycelium`) is 5 Python files; the model weights live on the local machine; queries never leave the device.

## Technical approach

**Base:** `google/gemma-4-e4b` (4B effective parameters, MoE-style efficient architecture)
**Tuning:** QLoRA-style LoRA via Apple MLX — *trained on the same M4 MacBook the CLI ships on.* No cloud. No external compute. `r=16`, `lora-alpha=32`, 16 transformer layers fine-tuned, ~30MB adapter.
**Corpus prep:** stdlib-only Python script (no dependencies on Kaggle, no preinstall) reads markdown + XeLaTeX, strips formatting, chunks on heading boundaries, emits instruction-tuned JSONL (~3k examples).
**Serving:** LoRA fused into base weights, packaged as Ollama image via the project's `scripts/mlx_to_ollama.sh` bridge. End-user pulls one image, runs `crowe-mycelium chat`, done.
**Identity:** The Modelfile's SYSTEM directive encodes Crowe Logic's identity rules ("never confabulate contamination diagnoses"; "ask for species before diagnosing"; "ground every claim in commercial practice"). These survive both the system-prompt overlay AND the LoRA fine-tune.

## Why it matters (Impact & Vision)

Commercial cultivation is one of the most under-served high-stakes domains for AI. A single bad agar diagnosis cascades into a contaminated tray, a contaminated block, a contaminated harvest. The economics of mushroom farming are tight; small operations *die* on three bad weeks.

The growers who most need this AI are the ones least able to access it: rural farmers, beginners trying to bootstrap a business out of a spare bedroom, operations in countries where stable internet is the exception. Putting a domain-grounded model on a 1-laptop, no-internet footprint changes the access equation.

This isn't a hypothetical user. The model is built on knowledge from Southwest Mushrooms — a real commercial cultivation operation in Phoenix, Arizona, that ships product to real customers. The LoRA training corpus *is* the company's institutional knowledge.

## Reproducibility

The repo is structured so a fresh teammate can reproduce the model with one `git clone` + 5 scripts:

```bash
git clone https://github.com/MichaelCrowe11/crowe-mycelium-cli
cd crowe-mycelium-cli

# 1. Build the training corpus from the canonical book + SOP sources
python scripts/prepare_corpus.py

# 2. Train the LoRA adapter on the local Mac (MLX, ~3-5h on M4)
python scripts/finetune_lora_mlx.py train

# 3. Merge adapter into base weights
python scripts/finetune_lora_mlx.py fuse

# 4. Build the Ollama image
./scripts/mlx_to_ollama.sh

# 5. Push to Ollama Hub
./scripts/setup_ollama_hub.sh push
```

Three alternate training paths are also committed (`finetune_lora_modal.py`, `submit_azure_ml.py`, the Kaggle notebook), each with explicit security/cost trade-offs documented. The default — MLX on the user's own Mac — is the one that matches the project's offline-cultivation thesis.

## What's distinctive about this submission

- **Identity-faithful through both training stages.** Phase 1 (Modelfile overlay) and Phase 2 (LoRA fine-tune) both anchor the model's behavior in cultivation-grounded rules. A grower asking "what is this pink patch?" gets the same diagnostic-discipline response from either phase.
- **Trained on the device it ships on.** No cloud, no Kaggle, no third-party in the loop. The HF_TOKEN never leaves the laptop. This isn't a corner cut for hackathon purposes — it's the actual security posture commercial cultivation operators need.
- **Real commercial corpus.** Two production-quality books and a 175-page commercial SOP, not a scraped corpus. Quality of training data shows up as quality of behavior.
- **Five-script pipeline.** Corpus prep, training, fusion, Ollama packaging, Hub push. All committed, all reproducible, all documented.

## License

- Code (CLI, scripts, notebooks): Apache 2.0
- Model weights: Gemma Terms of Use ([ai.google.dev/gemma/terms](https://ai.google.dev/gemma/terms))

## Acknowledgements

Built on **Gemma** by Google DeepMind. Submitted to the Gemma 4 Good Hackathon.
