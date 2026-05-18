#!/usr/bin/env python3
"""Polish Wav2Lip-synced frames with GFPGAN face restoration.

Wav2Lip pastes a 96×96 generated mouth region back into HD frames; the
result is a visibly soft patch over an otherwise sharp face. GFPGAN runs a
face-restoration GAN per frame so the mouth detail matches the surrounding
skin and the seam disappears.

Pipeline per act:
    decode video → frames → GFPGAN(face) → encode video → remux orig audio

Output: ``video/enhanced/act{1,2,4,5}.mp4`` at the same resolution + fps as
the input.

Requires ``GFPGANv1.4.pth`` in ``video/models/``; auto-downloads from the
TencentARC release on first run.

Runs on MPS where available, CPU otherwise. ~10-30 frames/sec on M-series.
"""
from __future__ import annotations

# --- shim: basicsr (a gfpgan dep) imports from a torchvision path that no
# longer exists in torchvision ≥ 0.17. Recreate the module pointing at the
# new location BEFORE basicsr is imported transitively by gfpgan.
import sys
import types
import torchvision.transforms.functional as _tvf

_shim = types.ModuleType("torchvision.transforms.functional_tensor")
_shim.rgb_to_grayscale = _tvf.rgb_to_grayscale
sys.modules["torchvision.transforms.functional_tensor"] = _shim
# ---

import argparse
import shutil
import subprocess
from pathlib import Path
from urllib.request import urlretrieve

import cv2
import numpy as np
import torch
from tqdm import tqdm

from gfpgan import GFPGANer


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNCED_DIR = REPO_ROOT / "video" / "synced"
ENHANCED_DIR = REPO_ROOT / "video" / "enhanced"
MODELS_DIR = REPO_ROOT / "video" / "models"
TMP_DIR = REPO_ROOT / "video" / "tmp_gfpgan"

GFPGAN_URL = (
    "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth"
)
GFPGAN_PATH = MODELS_DIR / "GFPGANv1.4.pth"


def _ensure_model():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if GFPGAN_PATH.exists() and GFPGAN_PATH.stat().st_size > 100_000_000:
        return
    print(f"  downloading GFPGANv1.4 ({GFPGAN_URL}) → {GFPGAN_PATH}")
    urlretrieve(GFPGAN_URL, GFPGAN_PATH)
    sz = GFPGAN_PATH.stat().st_size / 1e6
    print(f"  wrote {sz:.1f} MB")


def _video_fps(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]).decode().strip()
    num, den = out.split("/")
    return float(num) / float(den)


def _decode_frames(in_video: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(in_video),
        "-q:v", "1",
        str(out_dir / "frame_%05d.png"),
    ], check=True)
    return len(list(out_dir.glob("frame_*.png")))


def _encode_with_audio(frames_dir: Path, audio_src: Path, fps: float, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", f"{fps:g}",
        "-i", str(frames_dir / "frame_%05d.png"),
        "-i", str(audio_src),
        "-map", "0:v", "-map", "1:a",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out),
    ], check=True)


def _enhance_dir(restorer: GFPGANer, src_dir: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    paths = sorted(src_dir.glob("frame_*.png"))
    for p in tqdm(paths, desc=f"  {src_dir.parent.name}", unit="frame"):
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        # paste_back=True returns the full-res frame with the restored face
        # composited back in place.
        _, _, restored = restorer.enhance(
            img,
            has_aligned=False,
            only_center_face=True,
            paste_back=True,
        )
        # When no face is detected, restored is None — fall back to the
        # original so we never drop a frame.
        if restored is None:
            restored = img
        cv2.imwrite(str(dst_dir / p.name), restored)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--acts", default="1,2,4,5",
                        help="comma-separated act numbers")
    parser.add_argument("--keep-frames", action="store_true",
                        help="keep frame dirs after run (for debugging)")
    args = parser.parse_args()

    ENHANCED_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_model()

    device = "mps" if torch.backends.mps.is_available() else (
        "cuda" if torch.cuda.is_available() else "cpu"
    )
    print(f"  device: {device}")

    restorer = GFPGANer(
        model_path=str(GFPGAN_PATH),
        upscale=1,
        arch="clean",
        channel_multiplier=2,
        bg_upsampler=None,
        device=device,
    )

    for raw in args.acts.split(","):
        act = raw.strip()
        if not act:
            continue
        in_video = SYNCED_DIR / f"act{act}.mp4"
        out_video = ENHANCED_DIR / f"act{act}.mp4"
        if not in_video.exists():
            print(f"  act{act}: input missing, skip")
            continue
        if out_video.exists():
            print(f"  act{act}: enhanced exists, skip")
            continue

        print(f"\n=== act{act} ===")
        fps = _video_fps(in_video)
        print(f"  fps={fps:g}")

        src_frames = TMP_DIR / f"act{act}_raw"
        dst_frames = TMP_DIR / f"act{act}_enh"
        if src_frames.exists():
            shutil.rmtree(src_frames)
        if dst_frames.exists():
            shutil.rmtree(dst_frames)

        n = _decode_frames(in_video, src_frames)
        print(f"  decoded {n} frames")

        _enhance_dir(restorer, src_frames, dst_frames)
        _encode_with_audio(dst_frames, in_video, fps, out_video)
        sz = out_video.stat().st_size / 1e6
        print(f"  ✓ {out_video.name} ({sz:.1f} MB)")

        if not args.keep_frames:
            shutil.rmtree(src_frames)
            shutil.rmtree(dst_frames)

    print("\nDone. Polished clips in", ENHANCED_DIR)


if __name__ == "__main__":
    main()
