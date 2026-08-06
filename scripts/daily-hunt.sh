#!/bin/zsh
# Daily privacy-news hunt: runs Claude Code headless against HUNT.md.
# Invoked by cron; logs to logs/hunt-YYYY-MM-DD.log.
set -euo pipefail

ROOT="${0:A:h:h}"
cd "$ROOT"
mkdir -p logs

# cron runs with a minimal PATH; make sure claude + python3 resolve
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude)}"
LOG="logs/hunt-$(date +%F).log"

{
  echo "=== hunt started $(date) ==="
  "$CLAUDE_BIN" -p "Read HUNT.md in the current directory and execute it exactly. Today is $(date +%F)." \
    --permission-mode acceptEdits \
    --allowedTools "WebSearch" "WebFetch" "Read" "Write" "Edit" "Glob" "Grep" "Bash(python3 scripts/newsdb.py:*)" "Bash(python3 scripts/fetch_feeds.py:*)"
  echo "=== hunt finished $(date) ==="
} >> "$LOG" 2>&1
