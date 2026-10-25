#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ ! -x .venv/bin/python ]]; then
    if command -v python3.12 >/dev/null 2>&1; then
        python3.12 -m venv .venv
    else
        python3 -m venv .venv
    fi
fi
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install -r requirements.txt 'pyinstaller>=6.11,<7'
.venv/bin/python scripts/build_macos.py --format both
open dist
