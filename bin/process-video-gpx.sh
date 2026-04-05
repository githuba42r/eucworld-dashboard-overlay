#!/usr/bin/env bash
#
# Automatically process video files with GPX overlay using gopro-dashboard-overlay.
# Detects video orientation/resolution, generates appropriate layout XML,
# and renders the overlay with NVIDIA GPU encoding when available.
#
# Usage:
#   process-video-gpx.sh <video_file> <gpx_file> [output_file]
#   process-video-gpx.sh --batch <gpx_file> <video_file1> [video_file2] ...
#
# Options:
#   --batch           Process multiple videos with the same GPX file
#   --exclude <list>  Space-separated components to exclude (default: "heartbeat temperature cadence")
#   --speed-unit      Speed unit: kph, mph, knots (default: kph)
#   --font            Font path (default: auto-detect)
#   --no-gpu          Force CPU encoding even if NVIDIA GPU is available
#   --help            Show this help message

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$REPO_DIR/venv"

# Defaults
EXCLUDE="heartbeat temperature cadence"
SPEED_UNIT="kph"
FONT=""
FORCE_NO_GPU=false
BATCH_MODE=false
SHOW_FFMPEG=false
GPX_TIME_OFFSET=""

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo ":: $*"; }

usage() {
    sed -n '2,/^$/{ s/^# \?//; p }' "$0"
    exit 0
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)      usage ;;
        --batch)        BATCH_MODE=true; shift ;;
        --exclude)      shift; EXCLUDE="$1"; shift ;;
        --speed-unit)   shift; SPEED_UNIT="$1"; shift ;;
        --font)         shift; FONT="$1"; shift ;;
        --no-gpu)       FORCE_NO_GPU=true; shift ;;
        --show-ffmpeg)  SHOW_FFMPEG=true; shift ;;
        --gpx-time-offset) shift; GPX_TIME_OFFSET="$1"; shift ;;
        -*)             die "Unknown option: $1" ;;
        *)              POSITIONAL+=("$1"); shift ;;
    esac
done

# ---------------------------------------------------------------------------
# Resolve inputs
# ---------------------------------------------------------------------------
if $BATCH_MODE; then
    [[ ${#POSITIONAL[@]} -ge 2 ]] || die "Batch mode requires: --batch <gpx_file> <video1> [video2] ..."
    GPX_FILE="${POSITIONAL[0]}"
    VIDEO_FILES=("${POSITIONAL[@]:1}")
else
    [[ ${#POSITIONAL[@]} -ge 2 ]] || die "Usage: $0 <video_file> <gpx_file> [output_file]"
    VIDEO_FILES=("${POSITIONAL[0]}")
    GPX_FILE="${POSITIONAL[1]}"
    OUTPUT_OVERRIDE="${POSITIONAL[2]:-}"
fi

# Validate inputs
[[ -f "$GPX_FILE" ]] || die "GPX file not found: $GPX_FILE"
for vf in "${VIDEO_FILES[@]}"; do
    [[ -f "$vf" ]] || die "Video file not found: $vf"
done

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
if [[ -d "$VENV_DIR" ]]; then
    source "$VENV_DIR/bin/activate"
fi

command -v ffprobe >/dev/null 2>&1 || die "ffprobe not found in PATH"

# ---------------------------------------------------------------------------
# Auto-detect font
# ---------------------------------------------------------------------------
detect_font() {
    if [[ -n "$FONT" ]]; then
        [[ -f "$FONT" ]] || die "Font not found: $FONT"
        return
    fi
    # Try common fonts in order of preference
    for candidate in \
        "/usr/share/fonts/TTF/DejaVuSans.ttf" \
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" \
        "/usr/share/fonts/TTF/Roboto-Medium.ttf" \
        "/usr/share/fonts/truetype/roboto/Roboto-Medium.ttf" \
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf" \
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"; do
        if [[ -f "$candidate" ]]; then
            FONT="$candidate"
            return
        fi
    done
    # Fall back to fc-match
    if command -v fc-match >/dev/null 2>&1; then
        FONT="$(fc-match "DejaVu Sans" --format='%{file}')"
        [[ -f "$FONT" ]] && return
    fi
    die "No suitable font found. Use --font to specify one."
}
detect_font

# ---------------------------------------------------------------------------
# Detect NVIDIA GPU encoding support
# ---------------------------------------------------------------------------
detect_gpu() {
    if $FORCE_NO_GPU; then
        echo "none"
        return
    fi
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
        if ffmpeg -hide_banner -encoders 2>/dev/null | grep h264_nvenc >/dev/null 2>&1; then
            echo "nvgpu"
            return
        fi
    fi
    echo "none"
}

GPU_PROFILE="$(detect_gpu)"
if [[ "$GPU_PROFILE" != "none" ]]; then
    info "NVIDIA GPU detected — using hardware encoding (profile: $GPU_PROFILE)"
else
    info "No GPU acceleration — using CPU encoding (libx264)"
fi

# ---------------------------------------------------------------------------
# Analyse a video file and return: width height rotation effective_w effective_h
# ---------------------------------------------------------------------------
analyse_video() {
    local video="$1"
    local width height rotation

    # Get dimensions from first video stream (strip commas and whitespace from csv output)
    width="$(ffprobe -v quiet -select_streams v:0 -show_entries stream=width -of csv=p=0 "$video" 2>/dev/null | head -1 | tr -cd '0-9')"
    height="$(ffprobe -v quiet -select_streams v:0 -show_entries stream=height -of csv=p=0 "$video" 2>/dev/null | head -1 | tr -cd '0-9')"

    # Get rotation from display matrix side data
    rotation="$(ffprobe -v quiet -select_streams v:0 -show_entries stream_side_data=rotation -of csv=p=0 "$video" 2>/dev/null | head -1 | tr -cd '0-9-')"
    rotation="${rotation:-0}"

    # Calculate effective dimensions after rotation
    local eff_w eff_h
    case "$rotation" in
        -90|90|-270|270)
            eff_w="$height"
            eff_h="$width"
            ;;
        *)
            eff_w="$width"
            eff_h="$height"
            ;;
    esac

    echo "$width $height $rotation $eff_w $eff_h"
}

# ---------------------------------------------------------------------------
# Generate a layout XML for the given effective dimensions
# ---------------------------------------------------------------------------
generate_layout() {
    local eff_w="$1" eff_h="$2" output_xml="$3"

    # Calculate positions relative to frame size
    # Right-side elements anchored to right edge
    local right_x=$(( eff_w - 280 ))
    # Bottom elements
    local bottom_y=$(( eff_h - 108 ))
    # Speed display above bottom bar
    local speed_y=$(( eff_h - 400 ))
    # Chart position
    local chart_x=400
    local gradient_x=220

    cat > "$output_xml" <<XMLEOF
<layout>
    <composite x="260" y="30" name="date_and_time">
        <component type="datetime" x="0" y="0" format="%Y/%m/%d" size="16" align="right"/>
        <component type="datetime" x="0" y="24" format="%H:%M:%S.%f" truncate="5" size="32" align="right"/>
    </composite>

    <composite x="16" y="${speed_y}" name="big_mph">
        <component type="metric_unit" metric="speed" units="speed" size="16">{:~c}</component>
        <component type="metric" x="0" y="0" metric="speed" units="speed" dp="0" size="160" />
    </composite>

    <component type="chart" name="gradient_chart" x="${chart_x}" y="${bottom_y}" units="alt" />

    <composite x="${gradient_x}" y="${bottom_y}" name="gradient">
        <component type="text" x="70" y="0" size="16">SLOPE(%)</component>
        <component type="icon" x="0" y="0" file="slope-triangle.png" size="64"/>
        <component type="metric" x="70" y="18" metric="gradient" dp="0" size="32" />
    </composite>

    <composite x="16" y="${bottom_y}" name="altitude">
        <component type="metric_unit" x="70" y="0" metric="alt" units="alt" size="16">ALT({:~C})</component>
        <component type="icon" x="0" y="0" file="mountain.png" size="64"/>
        <component type="metric" x="70" y="18" metric="alt" units="alt" dp="0" size="32" />
    </composite>

    <component type="moving_map" name="moving_map" x="${right_x}" y="100" size="256" zoom="16" corner_radius="35"/>
    <component type="journey_map" name="journey_map" x="${right_x}" y="376" size="256" corner_radius="35"/>
</layout>
XMLEOF
}

# ---------------------------------------------------------------------------
# Check if a bundled layout exists for given dimensions
# ---------------------------------------------------------------------------
has_bundled_layout() {
    local w="$1" h="$2"
    [[ -f "$REPO_DIR/gopro_overlay/layouts/default-${w}x${h}.xml" ]]
}

# ---------------------------------------------------------------------------
# Process a single video
# ---------------------------------------------------------------------------
process_video() {
    local video="$1"
    local gpx="$2"
    local output="$3"

    info "Analysing: $(basename "$video")"

    read -r raw_w raw_h rotation eff_w eff_h <<< "$(analyse_video "$video")"
    info "  Raw: ${raw_w}x${raw_h} | Rotation: ${rotation}° | Effective: ${eff_w}x${eff_h}"

    # Build command arguments
    local -a cmd_args=(
        "--font" "$FONT"
        "--gpx" "$gpx"
        "--use-gpx-only"
        "--video-time-start" "video-created"
        "--overlay-size" "${eff_w}x${eff_h}"
        "--units-speed" "$SPEED_UNIT"
    )

    # Add exclusions
    if [[ -n "$EXCLUDE" ]]; then
        cmd_args+=("--exclude")
        for exc in $EXCLUDE; do
            cmd_args+=("$exc")
        done
    fi

    # Use bundled layout if available, otherwise generate custom XML
    if has_bundled_layout "$eff_w" "$eff_h"; then
        info "  Using bundled layout: default-${eff_w}x${eff_h}"
    else
        local layout_xml
        layout_xml="$(mktemp /tmp/layout-${eff_w}x${eff_h}-XXXXXX.xml)"
        generate_layout "$eff_w" "$eff_h" "$layout_xml"
        cmd_args+=("--layout" "xml" "--layout-xml" "$layout_xml")
        info "  Generated custom layout for ${eff_w}x${eff_h}"
    fi

    # Add GPX time offset if specified
    if [[ -n "$GPX_TIME_OFFSET" ]]; then
        cmd_args+=("--gpx-time-offset" "$GPX_TIME_OFFSET")
    fi

    # Add GPU profile if available
    if [[ "$GPU_PROFILE" != "none" ]]; then
        cmd_args+=("--profile" "$GPU_PROFILE")
    fi

    if $SHOW_FFMPEG; then
        cmd_args+=("--show-ffmpeg")
    fi

    # Input and output
    cmd_args+=("$video" "$output")

    info "  Output: $(basename "$output")"
    info "  Encoding: ${GPU_PROFILE:-cpu/libx264}"
    info "  Processing..."

    python "$SCRIPT_DIR/gopro-dashboard.py" "${cmd_args[@]}"

    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        info "  Done: $(basename "$output")"
    else
        echo "FAILED: $(basename "$video") (exit code $exit_code)" >&2
    fi

    # Clean up temp layout
    [[ -n "${layout_xml:-}" ]] && rm -f "$layout_xml"

    return $exit_code
}

# ---------------------------------------------------------------------------
# Generate output filename: input_overlay.MP4
# ---------------------------------------------------------------------------
make_output_name() {
    local input="$1"
    local dir ext base
    dir="$(dirname "$input")"
    ext="${input##*.}"
    base="$(basename "$input" ".$ext")"
    echo "${dir}/${base}_overlay.${ext}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
info "Font: $FONT"
info "Speed unit: $SPEED_UNIT"
info "Excluding: $EXCLUDE"
echo ""

FAILED=0
TOTAL=${#VIDEO_FILES[@]}

for video in "${VIDEO_FILES[@]}"; do
    if $BATCH_MODE || [[ -z "${OUTPUT_OVERRIDE:-}" ]]; then
        output="$(make_output_name "$video")"
    else
        output="$OUTPUT_OVERRIDE"
    fi

    if process_video "$video" "$GPX_FILE" "$output"; then
        echo ""
    else
        ((FAILED++)) || true
        echo ""
    fi
done

info "Complete: $((TOTAL - FAILED))/$TOTAL succeeded"
[[ $FAILED -eq 0 ]] || exit 1
