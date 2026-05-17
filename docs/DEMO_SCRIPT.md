# Demo Script — Act 3 of the Hackathon Video

**Companion to** `docs/VIDEO_SHOTLIST.md`. Pin this on the second monitor during the shoot.

The Act 3 demo (0:55 → 2:00 in the video) is the only segment that can't be faked or re-edited. The model's response streams live, on-camera, in airplane mode. This document exists so the demo lands first take.

---

## Pre-shoot checklist (15 minutes before "action")

```bash
# 1. Mac in airplane mode? (the on-screen caption depends on this being visible)
# Menu bar: airplane icon, "Wi-Fi: Off", "Bluetooth: Off"

# 2. Ollama daemon running locally
pgrep ollama || open -a Ollama && sleep 3

# 3. Model warm in memory (first-run load is 5-6 min; subsequent <1s)
ollama run Mcrowe1210/gemma-4-mycelium-e4b "ping" >/dev/null
#   ↑ The model is now resident. The on-camera response will be FAST.

# 4. Terminal cleared, history scrollback emptied (Cmd-K), font size bumped
clear

# 5. Test the planned demo prompt once OFF camera, confirm the response is
#    cultivation-faithful (asks for species, refuses to confabulate, etc.)
#    See "Vetted prompts" below.

# 6. Roll cameras. Type the prompt. Do not retype if you mistype — the
#    correction is part of the authenticity.
```

---

## Vetted prompts (pick ONE for the shoot)

Each prompt has been tested against the Phase 1 model. The expected behavior is documented so the editor knows what "the answer is good" looks like vs "shoot another take."

### Option A — the contamination question (RECOMMENDED for video)

```
why is my agar dish growing fuzzy green colonies near the edge but the center looks clean?
```

**Expected behavior** (matches the Modelfile's "never confabulate contamination" rule):
- First sentence asks for the species being grown.
- Acknowledges that green fuzz at the edge is *most commonly* Trichoderma but explicitly does not commit to a diagnosis.
- Provides a triage decision tree: continue running the dish? quarantine? toss the agar?
- Notes that "center clean, edge contaminated" is a classic pattern of *airborne* contamination on transfer, not substrate-borne.

**Why this is the video pick**: it shows the model doing the *opposite* of what a general-purpose chatbot would do. ChatGPT-class models confidently name a species; Gemma 4 Mycelium asks the question a senior grower would. That contrast is the whole pitch.

### Option B — the substrate question (BACKUP)

```
I want to grow Lion's Mane on a master's mix substrate. What hydration level should I aim for and how do I know when to inoculate?
```

**Expected behavior**:
- Hydration target: 60-65% (commercial Lion's Mane on hardwood-fuel mix)
- Inoculation timing tied to substrate temperature *post-sterilization*, not clock time
- Mentions cold-shock requirement for primordia formation later
- References the kind of language that's in the Mushroom Grower books

**Why this is the backup**: shorter response, less dramatic — but bulletproof. If Option A produces an unexpectedly short or generic response, switch to this.

### Option C — the diagnostic question (TIME-COMPRESSED BACKUP)

```
The pins on my Lion's Mane block are turning yellow and not developing. What should I check?
```

**Expected behavior**:
- Three checks: humidity (too high?), CO2 (too high?), light (too low?)
- Suggests a specific RH range (88-92%) and FAE schedule
- Acknowledges that yellow-then-stall is also a *genetic* problem with the dikaryon, not always environmental

**Why this is the compressed backup**: if the video runs long and you need a faster demo, this prompt resolves in ~150 tokens vs ~300+ for Options A and B.

---

## Hard requirements for the on-camera demo

These are non-negotiable; if any fail, re-shoot.

1. **The model must ask a clarifying question, not give a definitive diagnosis on first response.** This is the entire pitch. If the model confidently says "this is Trichoderma" without qualifications, that take is unusable — the Modelfile system prompt didn't load OR you accidentally pulled the base `gemma4:e4b` instead of `Mcrowe1210/gemma-4-mycelium-e4b`. Check with:
   ```bash
   ollama show Mcrowe1210/gemma-4-mycelium-e4b | head -20
   ```
   The `SYSTEM` section should contain "Never confabulate contamination diagnoses."

2. **The response must stream visibly, not appear all at once.** The streaming is what proves it's a real LLM running locally. If the response appears as a single block, your terminal is buffering — switch to `iTerm2` and disable "Faster scrolling that may affect interactivity" in Settings → Profiles → Terminal.

3. **The airplane mode indicator must be visible in at least one shot of the screen recording.** If you forgot to set airplane mode, the entire act is invalid. Cmd+Shift+5 → screen recording with menu bar visible.

4. **No "thinking" indicators or spinners during response.** Modern Ollama versions show a `⠋ Thinking...` spinner; this is fine. Older versions block the terminal which looks like a hang. If you see a hang of more than 3 seconds before tokens start streaming, kill it and retry — the model didn't warm.

---

## "What if the model gives a bad answer" recovery

| Symptom | Most likely cause | Recovery |
|---|---|---|
| Single-paragraph generic answer with no clarifying question | Modelfile SYSTEM didn't load. You're hitting base `gemma4:e4b`. | Verify with `ollama show <tag>`. Pull the right image. |
| Response confidently names a species | LoRA + Modelfile both undertrained the "ask first" pattern. Or you're on base gemma4. | Switch to backup prompt B. |
| Response trails off mid-sentence | Token budget too tight, or model evicted from memory. | `ollama run <tag> "ping"` to warm, then retry. |
| Response includes "As an AI language model..." | The Gemma base alignment leaked through the fine-tune. Rare but possible. | Use prompt option C — less alignment surface area. |
| Response is in the wrong language | Tokenizer encoding issue or chat template misapplied. | This shouldn't happen with Ollama-built images. If it does, rebuild via `./scripts/mlx_to_ollama.sh`. |

---

## Post-demo cleanup shot (Act 3 → Act 4 transition)

After the model's response finishes streaming (around 1:45 in the timeline):

1. Michael holds the dish up to compare to the response. **3-4 second hold** — judges need to register the dish ↔ answer cognitive loop. Don't rush.
2. He nods (subtly, not theatrical).
3. He uncaps a Sharpie and writes the diagnosis on the dish lid. Visible writing helps the cut.
4. Camera pulls back from the laptop → tilts up to Michael → soft cut to Act 4.

The Sharpie shot is the single most powerful frame in the whole video. It proves the model was used for a real decision, not just exhibited as a demo. Don't skip it.

---

## On-screen overlays (Act 3 specific)

These are the captions referenced in `VIDEO_SHOTLIST.md` Act 3, with timing locked:

| timestamp | text | duration | position |
|---|---|---|---|
| 1:00 | `Recorded in airplane mode. The model runs entirely on this laptop.` | 4s | full-width banner, top third |
| 1:14 | `Gemma 4 Mycelium · Mcrowe1210/gemma-4-mycelium-e4b` | 3s | lower-third, small |
| 1:22 | (no caption — response streams uncovered) | | |
| 1:55 | `~3 sec to first token · 26 tokens/sec on M4 MacBook` | 4s | lower-right, mono font |

The "3 sec / 26 tokens/sec" caption is what makes engineering-minded judges sit up. It's also factual (measured on the actual training Mac).
