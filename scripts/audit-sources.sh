#!/bin/zsh
# Monthly source-coverage audit — mechanical feed-health check plus a
# librarian-framed gap analysis (web_search) that proposes new primary sources
# and flags feeds to repair or cut. Costs ~$0.30-0.60 per run.
# Report is maintainer-only (data/reports/ is git-ignored, not deployed).
# Read data/reports/latest-source-audit.md, then edit data/sources.json by hand.
set -euo pipefail
ROOT="${0:A:h:h}"
cd "$ROOT"
mkdir -p logs
[ -f .env ] && set -a && source .env && set +a
{
  echo "=== source audit $(date) ==="
  .venv/bin/python scripts/summarize.py audit-sources
} >> "logs/audit-$(date +%F).log" 2>&1
echo "source audit done -> data/reports/latest-source-audit.md"
