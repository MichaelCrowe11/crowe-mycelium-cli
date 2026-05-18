#!/usr/bin/env bash
# Post-process polish on film_v3_branded.mp4:
#   - fade-in 0.6s at film start (over title card)
#   - fade-out 0.8s at film end (over outro card)
#   - lower-third overlay on Michael's first appearance
#       window: title (3s) + intro (8s) + 2s into Act 1 = roughly 11.0-14.5s
#   - subtle Crowe Logic corner watermark across the talking-head segments
#
# Output: video/final/film_v4_polished.mp4

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IN="${REPO_ROOT}/video/final/film_v3_branded.mp4"
OUT="${REPO_ROOT}/video/final/film_v4_polished.mp4"
LOWER3="${REPO_ROOT}/video/cards/lower_third.png"
WATERMARK="${REPO_ROOT}/video/cards/corner_watermark.png"

if [[ ! -f "$IN" ]]; then
    echo "abort: missing $IN — run 09_recut_branded.sh first"
    exit 1
fi

# Render the lower-third strip if not already present
if [[ ! -f "$LOWER3" ]]; then
    /Volumes/Elements/wav2lip-local/.venv/bin/python - <<'PY'
from PIL import Image, ImageDraw, ImageFont
W, H = 1280, 110
INK = (10, 10, 10, 230)
GOLD = (191, 166, 105)

img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
# semi-transparent ink panel
draw.rectangle([0, 0, W, H], fill=INK)
# Hairline gold border 1px on top
draw.rectangle([0, 0, W, 1], fill=GOLD)

try:
    name_font = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 28)
    role_font = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 18)
    pill_font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
except OSError:
    name_font = role_font = pill_font = ImageFont.load_default()

# Eyebrow pill
label = "  ".join(list("FOUNDER"))
bbox = draw.textbbox((0, 0), label, font=pill_font)
tw = bbox[2] - bbox[0]
th = bbox[3] - bbox[1]
pad_x, pad_y = 14, 6
pw = tw + pad_x * 2
ph = th + pad_y * 2
px, py = 60, 18
draw.rectangle([px, py, px + pw, py + ph], outline=(191, 166, 105, 110), width=1)
draw.ellipse([px + 8, py + ph//2 - 3, px + 14, py + ph//2 + 3], fill=GOLD)
draw.text((px + pad_x + 14, py + pad_y - 1), label, font=pill_font, fill=GOLD)

# Name
draw.text((60, 50), "Michael Crowe", font=name_font, fill=(245, 245, 245))
# Role / company
draw.text((260, 62), "Crowe Logic Inc.   southwestmushrooms.com", font=role_font, fill=(170, 170, 170))

out = "/Users/crowelogic/Projects/crowe-mycelium-cli/video/cards/lower_third.png"
img.save(out)
print(f"wrote {out}")
PY
fi

DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$IN")
FADE_OUT_START=$(awk "BEGIN{printf \"%.3f\", $DUR - 0.8}")

# Lower-third window: from 11.0s to 14.5s (during Act 1's first Michael cut)
# Watermark window: across all talking-head segments (rough cumulative ranges
# would over-complicate the filter; instead overlay it always at low opacity).

FILTER="
[0:v]fade=t=in:st=0:d=0.6:color=black,fade=t=out:st=${FADE_OUT_START}:d=0.8[v0];
[1:v]format=rgba,colorchannelmixer=aa=0.95[lt];
[v0][lt]overlay=x=0:y=H-h-40:enable='between(t,11.0,14.5)'[v1];
[2:v]format=rgba,colorchannelmixer=aa=0.55,scale=140:-1[wm];
[v1][wm]overlay=x=W-w-30:y=30[v]
"

ffmpeg -y -loglevel error \
    -i "$IN" \
    -i "$LOWER3" \
    -i "$WATERMARK" \
    -filter_complex "$FILTER" \
    -map "[v]" -map "0:a" \
    -pix_fmt yuv420p -c:v libx264 -preset slow -crf 18 \
    -c:a aac -b:a 192k -movflags +faststart \
    "$OUT"

echo "=== result ==="
ls -lh "$OUT"
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT"
