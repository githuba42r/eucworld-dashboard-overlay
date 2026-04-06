#!/usr/bin/env bash
#
# Launch the EUC World Dashboard Overlay visual layout editor.
#
# Sets up the Python virtual environment and dependencies if needed,
# then starts the editor. All arguments are passed through.
#
# Usage:
#   ./editor.sh
#   ./editor.sh --xlsx ride.xlsx --videos video1.MP4 video2.MP4
#   ./editor.sh --gpx ride.gpx --workdir ~/Videos/MyRide
#
# See docs/layout-editor-guide.md for full documentation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
EDITOR="$SCRIPT_DIR/bin/gopro-layout-editor.py"

# -- Set up virtual environment --
if [[ ! -d "$VENV_DIR" ]]; then
    echo ":: Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# Install/update dependencies if requirements.txt is newer than marker
MARKER="$VENV_DIR/.requirements-installed"
if [[ ! -f "$MARKER" ]] || [[ "$REQUIREMENTS" -nt "$MARKER" ]]; then
    echo ":: Installing dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -r "$REQUIREMENTS"
    # openpyxl needed for XLSX support
    pip install --quiet openpyxl
    touch "$MARKER"
fi

# -- Launch editor --
echo ":: Starting layout editor..."
python "$EDITOR" "$@"
