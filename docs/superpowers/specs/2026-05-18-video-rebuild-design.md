# Video Rebuild - Gemma 4 Mycelium Hackathon Submission

**Date:** 2026-05-18
**Status:** Design - pending approval
**Replaces:** `video/final/film_v7b_lipsync.mp4` (1280x720, 25fps, sync.so cloud lipsync)
**Deadline:** 2026-05-18 23:59 UTC (~21h from design time)

## Why a rebuild instead of a retouch

1. Current export is 1280x720 @ 25fps. Judges expect 1080p; the resolution
   alone undersells the work.
2. The lipsync surface in v7b uses the cloud sync.so pipeline. We want
   local-only authenticity to match the submission's offline-edge thesis.
3. Clip pool is shallow. The SWM YouTube archive (195K-subscriber channel,
   years of professionally shot facility footage) is a strictly stronger
   source than the 31-clip `tmp_real/` working set.
4. Title and end screens do not foreground the Crowe Logic corporate mark.
   The video is a Crowe Logic Inc. release; the hex-C should sit at center.

## Audience and rubric

Gemma 4 Good Hackathon judges. Rubric weights Impact & Vision (40) plus
Video Pitch & Storytelling (30) at 70 of 100. The video carries this
submission. Special Tech track (Offline / Edge AI).

## Design decisions (locked)

| decision | choice |
|---|---|
| Clip source | yt-dlp from SWM YouTube channel |
| Lipsync | None. Use real-speech moments from the archive. |
| Voice | Michael's actual voice from the clips. No ElevenLabs synthesis. |
| Music | Substrate or Substrate Companion instrumental bed under non-spoken segments. |
| Logo | Corporate hex-C mark (1024x1024 RGBA from crowelogic-website). |
| Title/end treatment | Static centered. No animation. |
| CTAs (end screen) | All four: `ollama pull` (primary), GitHub, Kaggle, crowelogic.com. |
| Resolution / fps | 1920x1080 @ 30fps |
| Codec / bitrate | H.264, ~25 Mbps target, AAC audio 192 kbps |
| Subtitles | Burned-in English |

## Visual spec

### Title card (0:00 - 0:05)

```
[ centered: corporate hex-C mark, ~30% frame height ]

         CROWE  LOGIC  PRESENTS

         Gemma 4 Mycelium
         Offline AI for Commercial Mushroom Cultivation

         Submission · Gemma 4 Good Hackathon · Special Tech Track
```

Background: dark neutral (matte black or near-black charcoal), no texture.
Type: a sans-serif system font that ships on every Mac (Helvetica Neue or
SF Pro). The mark sits on its own optical baseline above the wordmark.

### Lower-third (when Michael speaks)

```
Michael Crowe
Crowe Logic · Southwest Mushrooms
```

Bottom-left, 8% margin from edges. Small corporate mark to the left of the
name (32px equivalent at 1080p).

### End card (2:55 - 3:00, hold 5 seconds)

```
[ centered: corporate hex-C mark, ~25% frame height ]

         Gemma 4 Mycelium

         ollama pull Mcrowe1210/gemma-4-mycelium-e4b

         github.com/MichaelCrowe11/crowe-mycelium-cli
         kaggle.com/competitions/gemma-4-good-hackathon
         crowelogic.com/mycelium

         Built on Gemma · Released under Gemma Terms of Use
```

The `ollama pull` command is the largest secondary line (it's the conversion).
The three URLs sit in a smaller equal-weight row beneath.

Background: matches title card. Holds 5 seconds (extended end card) so
viewers can scan the URLs.

## Audio spec

- **Voice:** real Michael, from YouTube source clips. No synthesis.
- **Music:** one Substrate / Substrate Companion instrumental bed, ducked
  under any spoken audio. Per the project's global-sidechain feedback,
  any non-spoken layer must duck under primary voice via asplit.
- **Music ducks fully:** during the Act 3 demo segment (0:55 - 2:00) the
  music drops to silence so the terminal sounds and Michael's diagnostic
  reaction carry the moment.
- **Subtitles:** burned-in English, on every Michael line. Judges may
  watch muted.

## Scene plan

Mirrors the existing `docs/VIDEO_SHOTLIST.md` 5-act structure, but every
act's source switches from `video/source/act*.mp4` to clips pulled from
the SWM YouTube channel.

| act | window | function | source strategy |
|---|---|---|---|
| 1 | 0:00 - 0:25 | Cold open: contaminated dish, the stakes | YouTube: hunt for "contamination" / "agar" / "Trichoderma" content |
| 2 | 0:25 - 0:55 | The gap: AI doesn't reach the grow room | YouTube: facility wide shots, no-signal moments, hands-on work |
| 3 | 0:55 - 2:00 | The demo: live CLI in airplane mode | NEW screen recording, captured fresh (cannot reuse YouTube) |
| 4 | 2:00 - 2:30 | The model: Gemma attribution beat | YouTube: Michael at the laptop / direct-to-camera explainers |
| 5 | 2:30 - 3:00 | The vision: scale + close | YouTube: facility B-roll, Michael's direct address moments |

Act 3 is the only act that cannot be sourced from YouTube. It must be a
fresh screen capture of the live CLI in airplane mode, per the
non-negotiables in `docs/DEMO_SCRIPT.md`.

## Pipeline

```
1. yt-dlp: pull the channel's 30 highest-relevance videos to a scratch
   dir on /Volumes/Elements (NOT /tmp, per [[reference-audio-scratch-path]]).
   Channel handle: confirm at runtime (likely @MichaelCroweMycology
   per memory).

2. Whisper-transcribe each pulled video locally (whisper.cpp). Build a
   line-level index: timestamp -> spoken text. This is the search
   surface for matching the script.

3. Match script lines to real spoken moments. Output a cut list:
   per script beat, the (source_video, in_point, out_point) tuple.

4. Cut clips with ffmpeg -ss / -to / -c copy (lossless, no re-encode).
   Output: video/v8/scenes/<act>_<slot>.mp4

5. Build title.png and end.png at 1920x1080 from the corporate mark and
   the typography spec above. ImageMagick or a python Pillow script.

6. Build lower-third.png as a transparent overlay.

7. Re-record Act 3 in airplane mode per docs/DEMO_SCRIPT.md. This is
   the only original capture required.

8. Pick a Substrate instrumental from ~/Projects/talon or the album
   build directories. Confirm no sung vocals.

9. Assemble in ffmpeg: scenes -> concat -> overlay lower-thirds per
   timestamp -> mix audio (voice + ducked music) -> burn subs.

10. Export: H.264 1080p30, ~25 Mbps, AAC 192 kbps, movflags +faststart.

11. Upload to YouTube unlisted. Paste URL into docs/SUBMISSION.md.
```

## Failure modes and fallbacks

| risk | fallback |
|---|---|
| SWM YouTube channel lacks clean speech matching script beats | Drop to mixed strategy: real voice where it fits, ElevenLabs synthesis for gaps. Existing act1/2/4/5.mp3 already mastered. |
| whisper.cpp transcription too slow or inaccurate | Use yt-dlp `--write-auto-sub` to pull YouTube's auto-captions; less accurate but immediate. |
| Render timing collapses | Backup-plan from VIDEO_SHOTLIST.md: 90-second screen recording + 30-second talking-head intro + static "built on Gemma" card. Still a valid submission. |
| Phase 2 LoRA finishes during this work | Swap Modelfile FROM line, repackage Ollama tag, re-shoot Act 3 only. Other acts unaffected. |

## Time budget (rough)

| step | est. | cumulative |
|---|---|---|
| 1. yt-dlp pull | 30 min (network bound) | 0:30 |
| 2. whisper transcripts | 60 min | 1:30 |
| 3. match script to clips | 45 min (interactive) | 2:15 |
| 4. cut clips | 15 min | 2:30 |
| 5. cards (title/end/lower-third) | 30 min | 3:00 |
| 6. re-record Act 3 | 30 min | 3:30 |
| 7. assemble + mix + burn subs | 90 min | 5:00 |
| 8. review pass | 30 min | 5:30 |
| 9. YouTube upload + URL wire | 30 min | 6:00 |
| 10. Kaggle submit | 15 min | 6:15 |

Total ~6.25 hours. Comfortably within the ~21h deadline window even with
Kaggle training running in parallel.

## Out of scope

- Animated title sequence (decided: static)
- Corner watermark (decided: title + end branding is enough)
- 4K master (1080p is the spec)
- Phase 2 LoRA training (separate task, running on Kaggle independently)
- Soundtrack composition (reusing Substrate library)
