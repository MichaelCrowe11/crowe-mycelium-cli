# Crowe Mycelium

`crowe-mycelium` is the official Crowe Logic CLI for **Gemma 4 Mycelium** — a cultivation intelligence for commercial and at-home mushroom growers, built on Google Gemma 4.

It is the first open-sourced model in the Crowe Logic family. The model runs **fully offline** on your machine via Ollama, or against a **scale-to-zero cloud GPU** when you want speed without local hardware. The CLI adds real capabilities on top of the model: live **web search with citations**, a **deep ensemble** mode for hard diagnoses, and a streaming, brand-forward terminal experience.

Built with Gemma. Use of the model is subject to the [Gemma Terms of Use](https://ai.google.dev/gemma/terms).

---

## What is Gemma 4 Mycelium

- **Base model:** Google Gemma 4 (E4B)
- **Fine-tune:** a Crowe Logic mycology corpus — the Lion's Mane Commercial SOP, *The Mushroom Grower* Vol 1 and 2, and pattern data from the Mycelium EI Engine
- **Target user:** commercial and at-home growers, including operators in low-connectivity environments
- **Runtime:** fully offline via Ollama (default), or a scale-to-zero Modal GPU for the cloud path
- **Identity:** the model presents as Crowe Mycelium and is honest about its limits — it tells you when a question needs live data rather than guessing

## Why it exists

A grower in a fruiting room does not always have a reliable connection, and rarely has a data-center GPU. Crowe Mycelium is small enough to run on a laptop and answer cultivation questions in-line: substrate ratios, environmental controls, contamination differentials, yield optimization. When a question genuinely needs current information — this week's wholesale prices, a newly released strain — the CLI can search the web and ground the answer in real sources. When a diagnosis is hard, it can deliberate: draw several independent answers and reconcile them into one, with a confidence signal.

---

## Install

```bash
git clone https://github.com/MichaelCrowe11/crowe-mycelium-cli
cd crowe-mycelium-cli && pip install -e .
```

### Run it offline (Ollama)

```bash
brew install ollama
ollama serve &
ollama pull Mcrowe1210/gemma-4-mycelium-e4b
crowe-mycelium --local
```

To build the model image locally from the published Gemma 4 weights instead of pulling:

```bash
ollama create Mcrowe1210/gemma-4-mycelium-e4b -f modelfile/Modelfile
```

### Run it on the cloud (optional)

The cloud path serves the same model on a scale-to-zero Modal GPU (about $0 when idle; a short cold start on the first call after idle). With a Modal account configured:

```bash
modal deploy scripts/serve_ollama_modal.py
crowe-mycelium --cloud
```

---

## Use

```bash
crowe-mycelium                              # interactive chat (auto: cloud-first, local fallback)
crowe-mycelium --local                      # force the offline Ollama backend
crowe-mycelium --cloud                      # force the cloud backend
crowe-mycelium run "why is my agar pink?"   # one-shot (plain output when piped)
crowe-mycelium info                         # model + backend status
crowe-mycelium doctor                       # diagnose local + cloud reachability
crowe-mycelium serve                        # optional OpenAI-compatible /v1 gateway
```

### In a chat session

```
/search <query>     search the web and answer grounded, with citations
/deep <question>    deliberate: sample the model several times, then reconcile (best for hard diagnoses)
/deep web <q>       force a web search before the ensemble
/local /cloud /auto switch backend mid-session
/info /doctor       status
/reset /help /quit
```

You can also just ask naturally. "Search the web for new oyster strains" or "look up wholesale prices" runs a real search directly. A question that clearly needs current data prompts an offer to search.

### Web search (`/search`)

The model cannot browse on its own, so the CLI does it: it fetches results, injects them as grounding, and the model answers over them with inline `[1]` citations followed by a Sources list. The default provider is keyless DuckDuckGo; the searcher is provider-agnostic, so a Brave or Tavily key can drop in later.

### Deep mode (`/deep`)

For a tough call — a stalled flush, an ambiguous contamination — `/deep` draws several independent answers at a higher temperature, then a judge pass reconciles them into one best answer and ends with a confidence line, for example `agreement: 3/3 aligned`. It composes with web search: if the question needs live data, it grounds first. Hidden samples, one clean answer, an honest confidence signal.

---

## How it works

The CLI is intentionally small and layered, so the model can be reached the same way whether it runs on your laptop or in the cloud:

- **Backends** — `local` (Ollama), `cloud` (Modal GPU), and `auto` (cloud-first with local fallback) sit behind one interface. A reserved escalation seam is in place for a future hybrid-brain path.
- **Renderers** — a pipe-safe plain renderer for scripts and CI, and a Rich renderer for the terminal with live token streaming and an animated thinking indicator.
- **Grounding** — the web searcher and grounding layer are shared by `/search` and `/deep`.

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `OLLAMA_HOST` | Ollama daemon URL | `http://localhost:11434` |
| `CROWE_MYCELIUM_OLLAMA_TAG` | Ollama model tag to use | `Mcrowe1210/gemma-4-mycelium-e4b` |
| `CROWE_MYCELIUM_BACKEND` | `auto` / `local` / `cloud` | `auto` |
| `CROWE_MYCELIUM_DEEP_SAMPLES` | candidates drawn by `/deep` | `3` |
| `CROWE_MYCELIUM_DEEP_TEMPERATURE` | sampling temperature for `/deep` | `0.8` |
| `CROWE_MYCELIUM_SEARCH_PROVIDER` | search backend | `duckduckgo` |

## Why a separate CLI

`crowe-logic` (the universal Crowe Logic agent CLI) hosts the full CroweLM model chain, agents, and dozens of tools. `crowe-mycelium` is intentionally smaller: one model, one job, runs offline. The model itself is registered in both — see `crowe_mycelium/registry.json`.

---

## License and attribution

- **CLI source, system prompt, fine-tune recipe, evaluation harness:** Apache 2.0 (see `LICENSE`).
- **Model weights:** Google Gemma, under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms).

Gemma 4 Mycelium is a derivative of Google's Gemma 4 family. The "Gemma" name is retained in the model identifier per Google's naming guidelines. Crowe Logic provides the fine-tune, the prompt scaffolding, the CLI, and the cultivation knowledge.

Built with Gemma by Google DeepMind.
