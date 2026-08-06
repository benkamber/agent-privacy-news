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

.venv/bin/python scripts/newsdb.py build   # make sure ui/data.js is current

PROJECT="${CF_PAGES_PROJECT:-agent-privacy-news}"
npx wrangler pages deploy ui --project-name "$PROJECT" --commit-dirty=true
