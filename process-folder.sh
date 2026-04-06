#!/usr/bin/env bash
#
# Process all videos in a folder with the route file found in the same
# folder, using a standardised layout XML file.
#
# Automatically detects the route file (GPX, FIT, or XLSX) and all
# video files (MP4/mp4) in the target folder. Each video gets an
# overlay rendered using the specified layout.
#
# Usage:
#   ./process-folder.sh <layout.xml> <folder> [options]
#
# Examples:
#   ./process-folder.sh my-layout.xml ~/Videos/Ride-2026-04-05/
#   ./process-folder.sh my-layout.xml ~/Videos/Ride/ --speed-unit kph
#   ./process-folder.sh my-layout.xml ~/Videos/Ride/ --sample-duration 15
#   ./process-folder.sh my-layout.xml ~/Videos/Ride/ --gpx-time-offset -30
#
# Options (passed through to gopro-dashboard.py):
#   --speed-unit <kph|mph|knots>  Speed unit (default: kph)
#   --gpx-time-offset <seconds>   Shift GPX/video time alignment
#   --sample-duration <seconds>   Only render N seconds (for testing)
#   --no-gpu                      Disable GPU encoding
#   --map-style <style>           Map tile style (default: osm)
#
# The route file is auto-detected: first .xlsx, then .gpx, then .fit
# in the target folder. If multiple exist, XLSX takes priority.
#
# Output files are named <original>_overlay.<ext> in the same folder.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
DASHBOARD="$SCRIPT_DIR/bin/gopro-dashboard.py"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo ":: $*"; }

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <layout.xml> <folder> [options]"
    echo ""
    echo "Process all videos in <folder> with the route file found there,"
    echo "using the given layout XML for the overlay."
    echo ""
    echo "Options:"
    echo "  --speed-unit <unit>        kph, mph, or knots (default: kph)"
    echo "  --gpx-time-offset <secs>   Shift GPX/video alignment"
    echo "  --sample-duration <secs>   Render only N seconds (testing)"
    echo "  --no-gpu                   Disable NVIDIA GPU encoding"
    echo "  --map-style <style>        Map tile style (default: osm)"
    exit 0
fi

LAYOUT_XML="$1"
FOLDER="$2"
shift 2

[[ -f "$LAYOUT_XML" ]] || die "Layout file not found: $LAYOUT_XML"
[[ -d "$FOLDER" ]] || die "Folder not found: $FOLDER"

# Parse remaining options
SPEED_UNIT="kph"
GPX_TIME_OFFSET=""
SAMPLE_DURATION=""
NO_GPU=false
MAP_STYLE="osm"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --speed-unit)       shift; SPEED_UNIT="$1"; shift ;;
        --gpx-time-offset)  shift; GPX_TIME_OFFSET="$1"; shift ;;
        --sample-duration)  shift; SAMPLE_DURATION="$1"; shift ;;
        --no-gpu)           NO_GPU=true; shift ;;
        --map-style)        shift; MAP_STYLE="$1"; shift ;;
        *)                  die "Unknown option: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Virtual environment setup
# ---------------------------------------------------------------------------
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

MARKER="$VENV_DIR/.requirements-installed"
if [[ ! -f "$MARKER" ]] || [[ "$REQUIREMENTS" -nt "$MARKER" ]]; then
    info "Installing dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -r "$REQUIREMENTS"
    pip install --quiet openpyxl
    touch "$MARKER"
fi

# ---------------------------------------------------------------------------
# Auto-detect route file
# ---------------------------------------------------------------------------
ROUTE_FILE=""
ROUTE_ARG=""

# Priority: XLSX > GPX > FIT
for ext in xlsx gpx fit; do
    found=$(find "$FOLDER" -maxdepth 1 -iname "*.$ext" -type f | head -1)
    if [[ -n "$found" ]]; then
        ROUTE_FILE="$found"
        if [[ "$ext" == "xlsx" ]]; then
            ROUTE_ARG="--xlsx"
        else
            ROUTE_ARG="--gpx"
        fi
        break
    fi
done

[[ -n "$ROUTE_FILE" ]] || die "No route file (.xlsx, .gpx, or .fit) found in $FOLDER"
info "Route file: $ROUTE_FILE ($(echo "$ROUTE_ARG" | tr -d '-'))"

# ---------------------------------------------------------------------------
# Find videos
# ---------------------------------------------------------------------------
VIDEOS=()
while IFS= read -r -d '' vfile; do
    VIDEOS+=("$vfile")
done < <(find "$FOLDER" -maxdepth 1 \( -iname "*.mp4" -o -iname "*.MP4" \) -type f ! -name "*_overlay*" -print0 | sort -z)

[[ ${#VIDEOS[@]} -gt 0 ]] || die "No video files (.MP4/.mp4) found in $FOLDER"
info "Found ${#VIDEOS[@]} video(s)"

# ---------------------------------------------------------------------------
# Detect GPU
# ---------------------------------------------------------------------------
GPU_ARGS=()
if ! $NO_GPU; then
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
        if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_nvenc; then
            GPU_ARGS=("--profile" "nvgpu")
            info "NVIDIA GPU detected — using hardware encoding"
        fi
    fi
fi

if [[ ${#GPU_ARGS[@]} -eq 0 ]] && ! $NO_GPU; then
    info "No GPU acceleration — using CPU encoding"
fi

# ---------------------------------------------------------------------------
# Detect font
# ---------------------------------------------------------------------------
FONT=""
for candidate in \
    "/usr/share/fonts/TTF/DejaVuSans.ttf" \
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" \
    "/usr/share/fonts/TTF/Roboto-Medium.ttf" \
    "/usr/share/fonts/truetype/roboto/Roboto-Medium.ttf" \
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf" \
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"; do
    if [[ -f "$candidate" ]]; then
        FONT="$candidate"
        break
    fi
done
if [[ -z "$FONT" ]] && command -v fc-match >/dev/null 2>&1; then
    FONT="$(fc-match "DejaVu Sans" --format='%{file}')"
fi
[[ -n "$FONT" ]] || die "No suitable font found"
info "Font: $FONT"

# ---------------------------------------------------------------------------
# Process each video
# ---------------------------------------------------------------------------
info "Layout: $LAYOUT_XML"
info "Speed unit: $SPEED_UNIT"
[[ -n "$GPX_TIME_OFFSET" ]] && info "GPX time offset: ${GPX_TIME_OFFSET}s"
[[ -n "$SAMPLE_DURATION" ]] && info "Sample duration: ${SAMPLE_DURATION}s"
echo ""

FAILED=0
TOTAL=${#VIDEOS[@]}

for video in "${VIDEOS[@]}"; do
    base="$(basename "$video")"
    ext="${video##*.}"
    stem="$(basename "$video" ".$ext")"
    output="$(dirname "$video")/${stem}_overlay.${ext}"

    info "Processing: $base"

    # Detect video dimensions and rotation
    raw_w="$(ffprobe -v quiet -select_streams v:0 -show_entries stream=width -of csv=p=0 "$video" 2>/dev/null | head -1 | tr -cd '0-9')"
    raw_h="$(ffprobe -v quiet -select_streams v:0 -show_entries stream=height -of csv=p=0 "$video" 2>/dev/null | head -1 | tr -cd '0-9')"
    rotation="$(ffprobe -v quiet -select_streams v:0 -show_entries stream_side_data=rotation -of csv=p=0 "$video" 2>/dev/null | head -1 | tr -cd '0-9-')"
    rotation="${rotation:-0}"

    case "$rotation" in
        -90|90|-270|270) eff_w="$raw_h"; eff_h="$raw_w" ;;
        *)               eff_w="$raw_w"; eff_h="$raw_h" ;;
    esac

    info "  ${eff_w}x${eff_h} (rotation: ${rotation}°)"

    # Build command
    CMD=(
        python "$DASHBOARD"
        --font "$FONT"
        $ROUTE_ARG "$ROUTE_FILE"
        --use-gpx-only
        --video-time-start video-created
        --overlay-size "${eff_w}x${eff_h}"
        --units-speed "$SPEED_UNIT"
        --layout xml
        --layout-xml "$LAYOUT_XML"
        --map-style "$MAP_STYLE"
    )

    [[ -n "$GPX_TIME_OFFSET" ]] && CMD+=(--gpx-time-offset "$GPX_TIME_OFFSET")
    [[ -n "$SAMPLE_DURATION" ]] && CMD+=(--sample-duration "$SAMPLE_DURATION")
    [[ ${#GPU_ARGS[@]} -gt 0 ]] && CMD+=("${GPU_ARGS[@]}")

    CMD+=("$video" "$output")

    info "  Output: $(basename "$output")"

    if "${CMD[@]}"; then
        info "  Done: $(basename "$output")"
    else
        echo "  FAILED: $base" >&2
        ((FAILED++)) || true
    fi
    echo ""
done

info "Complete: $((TOTAL - FAILED))/$TOTAL succeeded"
[[ $FAILED -eq 0 ]] || exit 1
