#!/usr/bin/env bash
set -euo pipefail

echo "Processing DJI_20260328105859_0046_D.MP4..."
python "/home/philg/working/gopro-dashboard-overlay/bin/gopro-dashboard.py" \
    --font "/usr/share/fonts/TTF/DejaVuSans.ttf" \
    --gpx "/home/philg/Video/Fernvale - 2026-03-28/Fernvale - 2026-03-28.gpx" \
    --use-gpx-only \
    --video-time-start video-created \
    --overlay-size 1080x1920 \
    --units-speed kph \
    --layout xml \
    --layout-xml "/home/philg/working/gopro-dashboard-overlay/test-video01.xml" \
    --map-style osm \
    --gpx-time-offset 30.0 \
    --profile nvgpu \
    "/home/philg/Video/Fernvale - 2026-03-28/DJI_20260328105859_0046_D.MP4" \
    "/home/philg/Video/Fernvale - 2026-03-28/DJI_20260328105859_0046_D_overlay.MP4"

echo "Done."