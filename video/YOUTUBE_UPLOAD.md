# YouTube Upload Metadata - Gemma 4 Mycelium Demo

Paste-ready fields for uploading `video/v9/film_v9.mp4` to YouTube.

**Channel:** Michael Crowe Mycology (cleaner audience alignment than SWM for an AI/ML submission).
**Visibility:** Unlisted - Kaggle judges follow the link; avoid random discovery before judging ends.

---

## Title
```
Gemma 4 Mycelium - Offline AI for Commercial Mushroom Cultivation
```

## Description
```
Gemma 4 Mycelium is an offline Gemma 4 E4B cultivation assistant for
commercial and at-home mushroom growers, distributed as a self-contained
Ollama image that runs locally on a single laptop.

Submission to the Gemma 4 Good Hackathon - Special Tech Track (Offline / Edge AI).

- Why this exists: Fruiting rooms in basements, greenhouses on rural
  acreage, cold rooms in tunnel houses. The humidity that grows mushrooms
  also kills routers. Putting a domain-grounded model on a 1-laptop,
  no-internet footprint changes the access equation for growers.

- What's different: The system overlay enforces "never diagnose
  contamination without species, inoculation source, and visual context."
  The Phase 1 image ships this behavior through the Ollama Modelfile and
  is backed by 2.1M characters of prepared commercial cultivation corpus
  for the Phase 2 LoRA path.

Pull and run:
  ollama pull Mcrowe1210/gemma-4-mycelium-e4b
  pip install -e git+https://github.com/MichaelCrowe11/crowe-mycelium-cli.git
  crowe-mycelium chat

Links:
  Code:    https://github.com/MichaelCrowe11/crowe-mycelium-cli
  Model:   https://ollama.com/Mcrowe1210/gemma-4-mycelium-e4b
  LoRA:    https://huggingface.co/crowelogic/gemma-4-mycelium-e4b-lora

Built by Michael Crowe / Crowe Logic Inc. - solo developer, Phoenix AZ.
Cultivation corpus authored at Southwest Mushrooms.
```

## Tags
```
Gemma, Gemma 4, Hackathon, Offline AI, Edge AI, Mushroom Cultivation,
Mycology, LLM, Ollama, LoRA Fine-tuning, Open Source AI, On-Device AI,
Agriculture AI, Crowe Logic
```

## Category
Science & Technology

## Thumbnail
Upload: `video/cover_candidates/CHOSEN_kaggle_cover.jpg`
(1920x1080 - real SWM facility shot of Michael at the tissue-culture rack;
same image used for the Kaggle cover. YouTube will downscale automatically.)

## Audience
"No, it's not made for kids"

## Visibility
**Unlisted** (anyone with the link can watch - Kaggle judges will follow
the URL from the submission writeup; avoids random discovery during judging).

---

## After upload - copy the URL into:
1. `docs/SUBMISSION.md` - add as the demo-video line at top
2. Kaggle competition entry - "Video" field
