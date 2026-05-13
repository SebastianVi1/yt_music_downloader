#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
fi

if ! command -v ffmpeg &>/dev/null; then
    echo "⚠️  ffmpeg is not installed. Please install it:"
    echo "    sudo apt install ffmpeg"
    echo ""
fi

exec "$VENV_DIR/bin/python" "$SCRIPT_DIR/main.py"
