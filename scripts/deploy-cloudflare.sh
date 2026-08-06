#!/bin/zsh
# Publish the read-only UI to Cloudflare Pages so a team can browse it.
#
# One-time setup (run yourself, interactive):
#   npx wrangler login
# or set a token instead of logging in, in .env:
#   CLOUDFLARE_API_TOKEN=...   (a token with the "Cloudflare Pages: Edit" permission)
#   CLOUDFLARE_ACCOUNT_ID=...
#
# Then run this script to deploy or redeploy. It rebuilds ui/data.js first, so
# run it after a scan to refresh the public site. The published page has no
# Scan/Report/Synthesis buttons; those need the local server.
set -euo pipefail
ROOT="${0:A:h:h}"
cd "$ROOT"
[ -f .env ] && set -a && source .env && set +a
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"   # so cron can find node/npx

.venv/bin/python scripts/newsdb.py build   # make sure ui/data.js is current

PROJECT="${CF_PAGES_PROJECT:-agent-privacy-news}"
# create the project on first run; a no-op (ignored error) once it exists
npx wrangler pages project create "$PROJECT" --production-branch main 2>/dev/null || true
npx wrangler pages deploy ui --project-name "$PROJECT" --branch main --commit-dirty=true
