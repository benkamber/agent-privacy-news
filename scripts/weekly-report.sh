#!/bin/zsh
# Weekly privacy-engineering delta report — only what's new since the last report.
# Archived to data/reports/; open data/reports/latest.md to paste it.
set -euo pipefail
ROOT="${0:A:h:h}"
cd "$ROOT"
mkdir -p logs
[ -f .env ] && set -a && source .env && set +a
{
  echo "=== weekly report $(date) ==="
  .venv/bin/python scripts/summarize.py report
} >> "logs/report-$(date +%F).log" 2>&1
