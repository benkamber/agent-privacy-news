#!/bin/zsh
# Weekly deep privacy-engineering synthesis — reads each paper's full text and
# maps developments to a privacy-by-design gap map. Costs ~$1-1.5 per run.
# Archived to data/reports/; open data/reports/latest-synthesis.md.
set -euo pipefail
ROOT="${0:A:h:h}"
cd "$ROOT"
mkdir -p logs
[ -f .env ] && set -a && source .env && set +a
{
  echo "=== weekly synthesis $(date) ==="
  .venv/bin/python scripts/summarize.py synthesis
  ./scripts/deploy-cloudflare.sh || echo "deploy skipped (site not updated)"
} >> "logs/synthesis-$(date +%F).log" 2>&1
