---
license: gemma
base_model: google/gemma-4-e4b
tags:
  - mycology
  - cultivation
  - agriculture
  - gemma
  - ollama
  - edge
language:
  - en
pipeline_tag: text-generation
library_name: transformers
---

# Gemma 4 Mycelium

**Gemma 4 Mycelium** is a cultivation intelligence for commercial and at-home mushroom growers, fine-tuned from Google Gemma 4 (E4B) by Crowe Logic. It is small enough to run fully offline on a laptop and is designed to answer practical cultivation questions in the room where the work happens.

Built with Gemma. Use of this model is subject to the [Gemma Terms of Use](https://ai.google.dev/gemma/terms).

- **Developed by:** Crowe Logic
- **Model type:** decoder-only language model (Gemma 4 E4B fine-tune)
- **Language:** English
- **License:** Gemma Terms of Use (weights); Apache 2.0 (CLI, prompts, recipe)
- **Base model:** `google/gemma-4-e4b`
- **CLI host:** [`crowe-mycelium`](https://github.com/MichaelCrowe11/crowe-mycelium-cli)

## Intended use

Direct, practical guidance for mushroom cultivation: substrate preparation and ratios, environmental controls (temperature, humidity, fresh air exchange, light), contamination differentials, fruiting and pinning, and yield optimization. The model is built for growers, including operators in low-connectivity environments where a cloud model is not an option.

It presents itself as Crowe Mycelium and is instructed to be honest about its limits: when a question needs current or external information it will say so rather than fabricate, and the host CLI can then perform a real web search to ground the answer.

### Out of scope

- Identification of wild mushrooms for consumption. The model declines to ID for ingestion and recommends a local expert or mycological society.
- General-purpose assistance outside cultivation (it will give a brief honest answer and refocus).
- Medical, legal, or financial advice.

## How to use

The model is distributed for Ollama and is most easily used through the `crowe-mycelium` CLI.

```bash
# Pull the model
ollama pull Mcrowe1210/gemma-4-mycelium-e4b

# Install and run the CLI
pip install -e .            # from the crowe-mycelium-cli repo
crowe-mycelium --local
```

Or call Ollama directly:

```bash
ollama run Mcrowe1210/gemma-4-mycelium-e4b "What CO2 range should I target for oyster fruiting?"
```

The CLI adds web search (`/search`) for current-information questions and a deliberation mode (`/deep`) that samples the model several times and reconciles the answers for hard diagnoses.

## Training data

Fine-tuned on a Crowe Logic mycology corpus:

- The Lion's Mane Commercial Standard Operating Procedure
- *The Mushroom Grower* Volumes 1 and 2
- Operational pattern data from the Mycelium EI Engine

The corpus excludes customer data, proprietary internal documents, and any personally identifiable information.

## Limitations and responsible use

- **Small model.** At the E4B scale, the model can be confident and wrong, especially on edge cases. For hard diagnoses, use the CLI's `/deep` mode, which draws multiple independent answers and reports an agreement signal — treat that signal as a confidence cue, not a guarantee.
- **No live knowledge.** The model does not know current prices, recent strain releases, or anything past its training cut-off. Use `/search` for those.
- **Cultivation context matters.** Answers improve when you provide species, substrate, stage, and observed symptoms. The model is instructed to ask for missing information rather than guess.
- **Safety.** For wild-mushroom identification or ingestion questions, defer to a qualified local expert.

## Attribution

Gemma 4 Mycelium is a derivative of Google's Gemma 4 family. The "Gemma" name is retained in the model identifier per Google's naming guidelines. Crowe Logic provides the fine-tune, prompt scaffolding, CLI, and cultivation knowledge.

Built with Gemma by Google DeepMind.

## Citation

```
@software{crowe_mycelium_2026,
  author  = {Crowe Logic},
  title   = {Gemma 4 Mycelium: a cultivation intelligence built on Gemma 4},
  year    = {2026},
  url      = {https://github.com/MichaelCrowe11/crowe-mycelium-cli}
}
```
