#!/bin/zsh
# Launch the local UI with the on-demand Scan button.
ROOT="${0:A:h:h}"
cd "$ROOT"
[ -f .env ] && set -a && source .env && set +a
exec .venv/bin/python scripts/serve.py
