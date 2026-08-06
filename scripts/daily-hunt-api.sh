#!/bin/zsh
# API-only daily pipeline: pull feeds, then aggregate + summarize with Claude
# via the Anthropic API (no interactive agent). Needs ANTHROPIC_API_KEY.
# Swap the crontab entry to this script to use it as the daily driver.
set -euo pipefail

ROOT="${0:A:h:h}"
cd "$ROOT"
mkdir -p logs

# load a git-ignored .env if present (e.g. ANTHROPIC_API_KEY=sk-ant-...)
[ -f .env ] && set -a && source .env && set +a

LOG="logs/hunt-api-$(date +%F).log"
{
  echo "=== api hunt started $(date) ==="
  python3 scripts/fetch_feeds.py
  .venv/bin/python scripts/summarize.py run
  echo "=== api hunt finished $(date) ==="
} >> "$LOG" 2>&1
