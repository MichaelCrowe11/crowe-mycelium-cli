# Crowe Mycelium

`crowe-mycelium` is the official Crowe Logic CLI for **Gemma 4 Mycelium** — an offline cultivation intelligence built on Google Gemma 4.

It is the first open-sourced model in the Crowe Logic family. The model lives on Hugging Face and Ollama; this repo is the small, focused host that runs it.

## What is Gemma 4 Mycelium

- **Base model**: Google Gemma 4 (E4B)
- **Fine-tune**: Crowe Logic mycology corpus — Lion's Mane Commercial SOP, *The Mushroom Grower* Vol 1 & 2, and pattern data from the Mycelium EI Engine
- **Target user**: commercial and at-home mushroom growers, including operators in low-connectivity environments
- **Runtime**: fully offline via Ollama (default), llama.cpp, or LiteRT

## Install

```bash
git clone https://github.com/MichaelCrowe11/crowe-mycelium-cli
cd crowe-mycelium-cli && pip install -e .
```

You'll also need Ollama running locally:

```bash
brew install ollama
ollama serve &
ollama pull Mcrowe1210/gemma-4-mycelium-e4b
```

To build the model locally from the published Gemma 4 weights instead of pulling:

```bash
ollama create Mcrowe1210/gemma-4-mycelium-e4b -f modelfile/Modelfile
```

## Use

```bash
crowe-mycelium                              # interactive chat
crowe-mycelium run "why is my agar pink?"   # one-shot
crowe-mycelium info                         # model + backend status
crowe-mycelium models                       # list registered model
```

Environment overrides:

| variable | purpose |
|---|---|
| `OLLAMA_HOST` | Ollama daemon URL (default `http://localhost:11434`) |
| `CROWE_MYCELIUM_OLLAMA_TAG` | Override the Ollama model tag (e.g. for local GGUFs) |

## Why a separate CLI

`crowe-logic` (the universal Crowe Logic agent CLI) hosts the full CroweLM model chain, agents, and 79 tools. `crowe-mycelium` is intentionally smaller: one model, one job, runs offline. The model itself is registered in both CLIs — see `crowe_mycelium/registry.json` and the Crowe Logic Foundry `config/models.extra.json` entry for `gemma-4-mycelium-e4b`.

## License

- **CLI, prompts, fine-tune scripts** → Apache License 2.0 (see `LICENSE`)
- **Gemma 4 Mycelium model weights** → Gemma Terms of Use ([ai.google.dev/gemma/terms](https://ai.google.dev/gemma/terms))

Gemma 4 Mycelium retains "Gemma" in its name per Google's Gemma model naming requirements for derivatives.

## Acknowledgements

Built on **Gemma** by Google DeepMind. This project was developed for the [Gemma 4 Good Hackathon](https://kaggle.com/competitions/gemma-4-good-hackathon).
