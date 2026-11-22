#!/usr/bin/env sh
# Starts Turmo Screen on macOS / Linux (creates a local Python environment on first run).
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "First run: setting up Python environment..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
fi
exec .venv/bin/python -m turmoscreen "$@"
