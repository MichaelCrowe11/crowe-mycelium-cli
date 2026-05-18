#!/usr/bin/env python3
"""Cut scenes from the SWM YouTube pool per cut_list_manual.json.

Output: video/v8/scenes/act<N>_<slot>.mp4
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def find_source(video_dir: Path, video_id: str) -> Path | None:
    """Match by trailing YouTube ID (the bit after the last underscore in our filenames)."""
    for mp4 in video_dir.glob("*.mp4"):
        if video_id in mp4.stem:
            return mp4
    return None


def cut_scene(src: Path, in_sec: float, out_sec: float, dst: Path, mute: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Re-encode for clean concat later. Lossless copy with -c copy often
    # produces keyframe-misaligned scenes that fail to concat cleanly.
    args = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{in_sec}",
        "-to", f"{out_sec}",
        "-i", str(src),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
        "-r", "30",
    ]
    if mute:
        args += ["-an"]
    else:
        args += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    args += [str(dst)]
    subprocess.run(args, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut-list", default="video/v8/cut_list_manual.json")
    ap.add_argument("--video-dir", default="/Volumes/Elements/swm-yt-archive-2026-05-18/videos")
    ap.add_argument("--out-dir", default="video/v8/scenes")
    args = ap.parse_args()

    cut_list = json.loads(Path(args.cut_list).read_text())
    video_dir = Path(args.video_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for scene in cut_list["scenes"]:
        act = scene["act"]
        slot = scene["slot"]
        vid_id = scene["video_id"]
        src = find_source(video_dir, vid_id)
        if not src:
            print(f"  MISS source for {vid_id}, skipping {act}/{slot}")
            continue
        dst = out_dir / f"act{act}_{slot}.mp4"
        mute = scene.get("audio_mode") == "mute"
        print(f">> cut act{act}_{slot}  [{scene['in_sec']:.1f} - {scene['out_sec']:.1f}s] from {src.stem[:50]}...")
        cut_scene(src, scene["in_sec"], scene["out_sec"], dst, mute)

    print(f"\n>> scenes in {out_dir}:")
    for s in sorted(out_dir.glob("*.mp4")):
        sz = s.stat().st_size
        print(f"   {s.name}  {sz/1024/1024:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
