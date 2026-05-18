# Act 3 Recording Checklist

Full pre-shoot procedure: `docs/DEMO_SCRIPT.md`.

## Quick checklist

1. **Airplane mode on.** Wi-Fi off, Bluetooth off, menu bar shows the airplane icon. The whole submission rides on this being visible in at least one frame.

2. **Warm the model:**
   ```bash
   pgrep ollama || open -a Ollama && sleep 3
   ollama run Mcrowe1210/gemma-4-mycelium-e4b "ping" >/dev/null
   ```

3. **Terminal prep:**
   - iTerm at large font (Cmd-+ a few times)
   - `clear` then `printf '\e[3J'` to wipe scrollback

4. **Start screen recording:**
   - Cmd-Shift-5 → Record entire screen → Show menu bar (visible airplane icon)
   - Start

5. **Run the prompt** (Option A from DEMO_SCRIPT.md):
   ```bash
   ollama run Mcrowe1210/gemma-4-mycelium-e4b
   ```
   Then type:
   ```
   why is my agar dish growing fuzzy green colonies near the edge but the center looks clean?
   ```

6. **Let it stream.** Do NOT cut. The streaming itself is the proof. If the response confidently names a species without asking what mushroom you're growing, the Modelfile SYSTEM directive didn't load: verify with `ollama show Mcrowe1210/gemma-4-mycelium-e4b | head -20`.

7. **Stop recording** after the response finishes. Save as:
   ```
   ~/Projects/crowe-mycelium-cli/video/v8/scenes/act3_demo.mp4
   ```

8. **Tell me when done.** I'll re-assemble with Act 3 in place, generate subtitles, and we move to upload.

## Target length
~60-75 seconds. If response runs longer, OK — we can trim the tail in post.

## Hard requirements (re-shoot if any fail)
- Airplane icon visible in at least one frame
- Response streams visibly (not appears as a block)
- Model asks a clarifying question, doesn't diagnose definitively first
