#!/usr/bin/env bash
# Cross-platform bootstrap (macOS / Linux) for the AI Tutor.
set -euo pipefail
cd "$(dirname "$0")"

VENV=.venv
if [ ! -x "$VENV/bin/python" ]; then
  echo "[init] Creating virtual environment..."
  python3 -m venv "$VENV"
fi

if ! "$VENV/bin/python" -c "import google.genai, matplotlib, numpy" 2>/dev/null; then
  if [ -f requirements.txt ]; then
    "$VENV/bin/pip" install -r requirements.txt
  else
    echo "[init] Dependencies missing and no requirements.txt found."
    echo "[init] Install google-genai, matplotlib and numpy into the venv."
  fi
fi

"$VENV/bin/python" main.py "$@"
