#!/usr/bin/env bash
# Synthesize the demo video for GET /watch/demo.
#
# Why this exists: both shipped samples (data/samples/pitch.mp4 and
# data/samples/jfk.mp4) have all-black video tracks (mean frame
# brightness 0.0 at every sampled timestamp) — they are audio-led files
# and cannot serve as player footage. This script builds a presentable
# track instead: one product-card slide per demo product (name + price,
# 7.5 s each) over the REAL audio track of pitch.mp4 (~22.3 s).
#
# Output: data/samples/demo_watch.mp4 (640x360, H.264 + AAC).
#
# The output is a binary file and CANNOT be pushed through the GitHub
# connector's UTF-8-only snapshot push, so it is intentionally NOT
# committed: after cloning, run this script once to recreate it. The
# /watch/demo page shows an animated slide fallback when the file is
# absent, so the page still demos without it.
#
# Usage: bash scripts/generate_demo_watch_video.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/data/samples/pitch.mp4"
OUT="$ROOT/data/samples/demo_watch.mp4"
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

[ -f "$SRC" ] || { echo "missing source audio/video: $SRC" >&2; exit 1; }
[ -f "$FONT" ] || { echo "missing font: $FONT" >&2; exit 1; }

# Each slide: solid background + product name + price, 7.5 s at 30 fps.
# drawtext text is single-quoted inside the filter; product names contain
# no colons or quotes, and the leading $ is literal for drawtext.
mk_slide() {
  local bg="$1" name="$2" price="$3"
  echo "color=c=${bg}:s=640x360:r=30:d=7.5,drawtext=fontfile=${FONT}:text='${name}':fontsize=44:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-30,drawtext=fontfile=${FONT}:text='\$$price':fontsize=36:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2+30,format=yuv420p"
}

ffmpeg -y -v error \
  -filter_complex \
    "$(mk_slide 0x8c4a3c 'Handmade Ceramic Mug' '20.00')[s0];$(mk_slide 0x5a4632 'Walnut Cutting Board' '45.00')[s1];$(mk_slide 0x3f5a44 'Organic Cotton Tote Bag' '12.00')[s2];[s0][s1][s2]concat=n=3:v=1:a=0[v]" \
  -i "$SRC" \
  -map "[v]" -map 0:a -c:v libx264 -preset veryfast -crf 23 \
  -c:a aac -b:a 96k -shortest "$OUT"

ffprobe -v error -show_entries stream=codec_type,width,height,duration \
  -of default=noprint_wrappers=1 "$OUT"
echo "wrote $OUT"
