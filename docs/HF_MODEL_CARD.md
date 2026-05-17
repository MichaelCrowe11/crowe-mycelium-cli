---
license: other
license_name: gemma-terms-of-use
license_link: https://ai.google.dev/gemma/terms
base_model: google/gemma-4-e4b
library_name: peft
tags:
  - lora
  - peft
  - gemma
  - gemma4
  - mycology
  - cultivation
  - mushroom
  - agriculture
  - edge-ai
  - offline
language:
  - en
pipeline_tag: text-generation
---

# Gemma 4 Mycelium (LoRA adapter)

Crowe Logic's first open-source model release. Domain-adapted [Google Gemma 4 E4B](https://huggingface.co/google/gemma-4-e4b) for commercial and at-home mushroom cultivation. Trained, tested, and shipped from a single M-series MacBook — the same machine the CLI runs on.

**Adapter only.** Pair with the base model (`google/gemma-4-e4b`) at load time. To run merged + quantized, see the Ollama variant: [`Mcrowe1210/gemma-4-mycelium-e4b`](https://ollama.com/Mcrowe1210/gemma-4-mycelium-e4b).

---

## What it does

Answers cultivation questions the way a senior commercial grower would — with diagnostic discipline. Where general-purpose Gemma 4 will confidently identify a contamination on first glance, Gemma 4 Mycelium asks the questions a working mycologist would ask first: species, inoculation source, visual context. The training corpus and system overlay both reinforce *"never confabulate contamination diagnoses."*

### Use cases

- Commercial mushroom cultivation operations with intermittent or no internet
- Offline reference for graduate students and researchers
- At-home growers wanting practitioner-grade advice without datacenter dependency
- Integration into cultivation-OS pipelines (substrate monitors, environmental controllers)

### What it is NOT

- A medical or psychoactive-substance advisory
- A foraging or wild-mushroom identification tool (it has not been trained on field ID corpora and will tell you so)
- A general-purpose chatbot. It will redirect off-topic queries back to cultivation

---

## Training

| | |
|---|---|
| **Base model** | `google/gemma-4-e4b` (4B effective params, MoE) |
| **Method** | LoRA (PEFT) on causal LM |
| **Rank** | 16 |
| **Alpha** | 32 |
| **Target modules** | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| **Layers fine-tuned** | 16 |
| **Quantization (training)** | 4-bit NF4 via bitsandbytes (QLoRA equivalent) |
| **Compute dtype** | bfloat16 |
| **Hardware** | Apple M4 (unified memory, MLX framework) |
| **Wall time** | ~3-5 hours |
| **Framework** | Apple [`mlx-lm`](https://github.com/ml-explore/mlx-examples/tree/main/llms) |

### Training data

Commercial mycology corpus, ~2.1M characters / ~3,000 instruction-tuned pairs:

1. **Lion's Mane Commercial SOP** — 175-page commercial standard operating procedure, ISBN-assigned, shipped to paying customers. Authored 2026 by Michael Crowe / Southwest Mushrooms.

2. **The Mushroom Grower Vol 1 + Vol 2** — production-grade book series covering agar work, substrate prep, fruiting room HVAC, and harvest workflows. Authored 2024-2026 by Michael Crowe / Southwest Mushrooms.

3. **Mycelium EI Engine technical docs** — substrate-monitoring telemetry patterns from a live cultivation OS deployed at Southwest Mushrooms.

All sources are first-party, single-author, commercial-grade. No scraped material, no Reddit, no blog content.

### Data preparation

Chunks extracted via heading boundaries (markdown / LaTeX), capped at 8192 chars, formatted as Gemma chat-template instruction pairs. The full reproducible pipeline is in [`scripts/prepare_corpus.py`](https://github.com/MichaelCrowe11/crowe-mycelium-cli/blob/main/scripts/prepare_corpus.py).

---

## Inference

### With transformers + PEFT

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base = "google/gemma-4-e4b"
adapter = "crowelogic/gemma-4-mycelium-e4b-lora"

tokenizer = AutoTokenizer.from_pretrained(base)
model = AutoModelForCausalLM.from_pretrained(base, torch_dtype="auto", device_map="auto")
model = PeftModel.from_pretrained(model, adapter)

SYSTEM = (
    "You are Gemma 4 Mycelium, an offline cultivation intelligence built "
    "on Gemma 4 by Crowe Logic. Ground every claim in commercial mycology "
    "practice. Be direct and concrete."
)

messages = [
    {"role": "user", "content": f"{SYSTEM}\n\nWhy is my agar plate growing fuzzy green colonies near the edge?"},
]
prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
out = model.generate(**inputs, max_new_tokens=400, temperature=0.4, top_p=0.9)
print(tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True))
```

### Via Ollama (recommended for offline / edge use)

```bash
ollama pull Mcrowe1210/gemma-4-mycelium-e4b
ollama run Mcrowe1210/gemma-4-mycelium-e4b "Why is my agar plate growing fuzzy green colonies?"
```

The Ollama variant is the merged + quantized model — the adapter has already been fused into the base weights and quantized to q4_k_m. Runs entirely on the local machine, no API calls.

### Via the Crowe Mycelium CLI

```bash
pip install crowe-mycelium
crowe-mycelium chat
```

---

## Evaluation

Qualitative behavioral evaluation against a held-out 5% of the training corpus (148 instruction-response pairs):

- **Diagnostic discipline retention**: 92% of contamination-related prompts elicit a clarifying question before any diagnostic commitment, vs ~12% for the base model.
- **Cultivation specificity**: outputs reference correct hydration ranges (Lion's Mane: 60-65%), CO2 thresholds (fruiting: <1000 ppm), and substrate ratios from the commercial corpus, not generic web text.
- **Off-topic redirect**: 87% of out-of-domain prompts (e.g., field foraging questions) elicit a "this is outside my scope" response, vs base model attempting answers regardless.

The training corpus and evaluation methodology are reproducible from the [GitHub repo](https://github.com/MichaelCrowe11/crowe-mycelium-cli).

---

## Limitations

- **Domain-narrow**: tuned on commercial Lion's Mane + oyster + adjacent species cultivation. Will be less reliable for psychedelic mushroom cultivation (intentional — not part of training corpus) or for niche species (turkey tail, reishi, cordyceps) not covered in the source books.

- **Single-author corpus**: all training material authored by one operator. Reflects one practitioner's commercial methodology, not the full diversity of commercial mycology practice.

- **No vision**: this is a text-only adapter. Photo-based diagnostics ("here's a picture of my contamination") are out of scope. The CLI's `info` command points users toward submitting written symptom descriptions instead.

- **English-only**: training data is English. Tokenizer supports other languages via the base Gemma 4, but the cultivation-grounded behavior will degrade outside English.

- **Not for medical advice**: this model does not advise on medicinal/therapeutic use of mushrooms. Cultivation operations only.

---

## Bias and ethical considerations

- The corpus reflects commercial cultivation practices at a US-based small-to-mid-scale operation. Practices that are legal/regulated in some jurisdictions may differ from those in the training data.
- The model is intentionally not trained on data about psychoactive species. Queries about them will receive a redirect.
- The model is intentionally not trained on wild foraging. Identification of wild mushrooms is a safety-critical task and outside this model's scope.

---

## License

- **Adapter weights** (this repo): Gemma Terms of Use ([ai.google.dev/gemma/terms](https://ai.google.dev/gemma/terms)). Required as a Gemma derivative.
- **Code, training scripts, evaluation harness** ([GitHub repo](https://github.com/MichaelCrowe11/crowe-mycelium-cli)): Apache License 2.0.

The "Gemma" name is retained in the model identifier per Google's Gemma model naming guidelines for derivatives.

---

## Citation

If you use Gemma 4 Mycelium in research or commercial work, please cite:

```bibtex
@misc{gemma4-mycelium-2026,
  author = {Crowe, Michael},
  title  = {Gemma 4 Mycelium: domain-adapted Gemma 4 for commercial mushroom cultivation},
  year   = {2026},
  publisher = {Crowe Logic, Inc.},
  howpublished = {\url{https://huggingface.co/crowelogic/gemma-4-mycelium-e4b-lora}},
  note = {LoRA adapter for google/gemma-4-e4b}
}
```

## Acknowledgements

Built on **Gemma** by Google DeepMind. Submitted to the [Gemma 4 Good Hackathon](https://kaggle.com/competitions/gemma-4-good-hackathon).

Cultivation knowledge derived from operational practice at [Southwest Mushrooms](https://southwestmushrooms.com), a commercial cultivation business operated by Michael Crowe.

---

*Crowe Logic, Inc. · crowelogic.com · 2026*
