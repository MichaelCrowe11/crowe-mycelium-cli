#!/usr/bin/env python3
"""Build the v10 contest video from voice, mobile UI, b-roll, and Substrate music."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "video"
V10 = VIDEO / "v10"
SEGS = V10 / "segs"
SEGS.mkdir(parents=True, exist_ok=True)
MANIFEST = V10 / "audio" / "manifest.json"
VOICE = V10 / "audio" / "voice.wav"
MUSIC = Path("/Volumes/Elements/Substrate_Final_Release_Instrumental/AlbumMasters/mp3_320/08 - The Engine's Reply - Album Master.mp3")
OUT = V10 / "film_v10.mp4"

VF = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"


def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd)


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(proc.stdout.strip())


def clip(name: str, src: Path, start: float, dur: float) -> Path:
    out = SEGS / f"{name}.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-stream_loop",
            "-1",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{dur:.3f}",
            "-i",
            str(src),
            "-an",
            "-vf",
            VF,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    print(f"{name:20s} {dur:5.2f}s  {src.relative_to(ROOT) if src.is_relative_to(ROOT) else src.name}")
    return out


def build_segments() -> list[Path]:
    manifest = json.loads(MANIFEST.read_text())
    acts = manifest["acts"]
    gap = 0.70
    durations = {act["act"]: float(act["duration"]) + gap for act in acts}
    files: list[Path] = []

    files.append(clip("01_real_growroom", VIDEO / "source" / "act1.mp4", 0, durations[1]))
    files.append(clip("02_mobile_case", V10 / "usecase_ui.mp4", 0, durations[2]))
    files.append(clip("03_mobile_triage", V10 / "usecase_ui.mp4", 21, durations[3]))

    act4 = durations[4]
    lab_a = min(10.0, act4)
    data = min(8.0, max(0.0, act4 - lab_a))
    lab_b = max(0.0, act4 - lab_a - data)
    files.append(clip("04_lab_model_a", VIDEO / "source" / "act4.mp4", 0, lab_a))
    if data > 0.1:
        files.append(clip("05_datacenter", VIDEO / "sora" / "03-datacenter-cold.mp4", 0, data))
    if lab_b > 0.1:
        files.append(clip("06_lab_model_b", VIDEO / "source" / "act2.mp4", 8, lab_b))

    files.append(clip("07_close", VIDEO / "source" / "act5.mp4", 0, durations[5]))
    return files


def concat(files: list[Path]) -> Path:
    list_file = SEGS / "concat.txt"
    list_file.write_text("".join(f"file '{path}'\n" for path in files))
    silent = V10 / "video_silent.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "copy",
            "-an",
            str(silent),
        ]
    )
    return silent


def mix(silent: Path) -> None:
    dur = probe_duration(silent)
    music_start = 20.0
    fade_out_start = max(0.0, dur - 3.0)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(silent),
            "-i",
            str(VOICE),
            "-ss",
            f"{music_start:.3f}",
            "-t",
            f"{dur:.3f}",
            "-i",
            str(MUSIC),
            "-filter_complex",
            (
                "[1:a]volume=1.0[voice];"
                f"[2:a]volume=0.16,afade=t=in:st=0:d=2.5,afade=t=out:st={fade_out_start:.3f}:d=3[bed];"
                "[voice][bed]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[aout]"
            ),
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-shortest",
            "-movflags",
            "+faststart",
            str(OUT),
        ]
    )
    print(f"wrote {OUT} duration={probe_duration(OUT):.2f}s size={OUT.stat().st_size:,}")


def main() -> int:
    if not VOICE.exists():
        raise SystemExit(f"missing voice: {VOICE}")
    if not (V10 / "usecase_ui.mp4").exists():
        raise SystemExit("missing usecase_ui.mp4; run scripts/video/v10_make_usecase_ui.py")
    files = build_segments()
    silent = concat(files)
    mix(silent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
