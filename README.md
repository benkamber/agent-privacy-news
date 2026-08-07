# agent-privacy-news

A self-updating tracker for privacy, security, and legal news in the agentic AI space. It covers attacks and data leakage through the tools agents use, Model Context Protocol (MCP) server vulnerabilities, agent-to-agent identity and authentication, and the wider cloud-platform and regulatory picture. It pulls from about 45 sources and uses Claude to pick and summarize the stories that matter. Each story is scored on three lenses (privacy, security, law) and tagged with subtopics in all three domains (prompt injection, supply chain, PETs, the EU AI Act, and so on), so a privacy engineer, a security analyst, or a policy lead can each filter to what they care about. It serves a local web page with per-lens daily digests and a deep weekly synthesis that reads each paper in full.

Nothing has to be hosted. It runs on your machine and writes plain files. You can also publish a read-only copy to Cloudflare Pages for a team to browse.

## What you need

- Python 3.9 or newer.
- An Anthropic API key. The summarization runs on Claude. Get a key at [console.anthropic.com](https://console.anthropic.com).
- A browser, for the local UI. Optional, since everything also runs from the command line.

A typical daily run costs a few cents of Claude usage. The deep weekly synthesis costs about a dollar because it reads the source papers.

## Install

```sh
git clone https://github.com/benkamber/agent-privacy-news.git
cd agent-privacy-news
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Set your API key

Copy the example file, then put your real key in the copy:

```sh
cp .env.example .env
# open .env and replace the placeholder with your key
```

`.env` is git-ignored, so the key stays on your machine. Every script loads it automatically.

## Load it

Start the local UI:

```sh
./scripts/ui.sh
```

That prints a `http://127.0.0.1:<port>` address and opens it in your browser. On a first run the page is empty. Click **Scan now**. The tool pulls the feeds, has Claude select and summarize the relevant stories, scores them on all three lenses, and writes today's digests. A scan takes about a minute. The page refreshes itself when the scan finishes.

Prefer the command line? This does the same work without the server:

```sh
.venv/bin/python scripts/summarize.py run
open ui/index.html      # macOS; or open the file in any browser
```

## The interface

The page has a news list, a digest panel, and a synthesis banner across the top.

**Scan now** pulls fresh news and summarizes it. The freshness pill next to it turns green under a day old, amber under three days, red beyond that.

**New since your last visit** is a cookieless, per-browser count. The tool remembers, in your browser's local storage only, the newest item you have seen; on your next visit it flags what arrived since and labels each new card "new as of" its timestamp. Nothing about you leaves the page.

**Lenses** (🔒 Privacy, 🛡 Security, ⚖ Law) each filter the list to stories that matter to that audience, rank them by relevance, and add a one-line note per story: which control it informs for privacy, which defense or threat for security, which obligation or risk for law. Turning on a single lens also switches the daily digest panel to that lens's cut and points the synthesis panel at that lens's briefing. The lenses are multi-select: turn on two and the list narrows to the cross-cutting stories relevant to both, ranked by combined relevance, with each lens's angle on the card.

**Subtopic** chips filter by theme within three domains. Privacy covers data governance, PETs, consent, data minimization, deletion and erasure, and the rest. Security covers prompt injection, data exfiltration, supply chain, identity, sandbox escape, and so on. Legal covers the EU AI Act, GDPR, US state privacy law, FTC actions, liability, and more. Chips and card badges are color-coded by domain. The **Sort** control orders the list by newest, by importance, or grouped by subtopic, and a date-range filter narrows to the last day through the last 90 days.

**Daily digest** shows a plain-spoken TL;DR plus the top stories. With one lens active it swaps to that lens's cut: the security digest leads with what to detect or patch, the legal digest with obligations and enforcement, the privacy digest with controls to build. With no lens, or more than one, it shows the general cross-lens digest.

**Weekly synthesis** sits at the top as a standing panel and reads each paper's full text before writing a plain-language, mechanism-level briefing: the longer-term trends, a per-development breakdown of what it is and how it works and what it means for your roadmap, a gap map of what the industry shipped this window versus what is still missing, and what the evidence says to be wary of. The privacy synthesis runs automatically each week. The security and legal syntheses are generated on demand: select that lens and press **Generate** (local server only, since each run costs a few minutes and about a dollar). Each panel names its lens and the date it last ran. The published site shows whichever syntheses have been generated, read-only.

## Publish to the web (Cloudflare Pages)

The UI and its data hold no secrets, so you can publish a read-only copy for a team to browse. The published page shows the news, lenses, subtopics, digests, methodology, and any generated syntheses, but not the Scan or Generate buttons, since those need the local server.

One-time, authenticate wrangler (opens a browser):

```sh
npx wrangler login
```

Then deploy or redeploy:

```sh
./scripts/deploy-cloudflare.sh
```

That rebuilds `ui/data.js`, regenerates the methodology page from the source register, and pushes the `ui/` directory to a Cloudflare Pages project named `agent-privacy-news`. Cloudflare prints the public URL. `scripts/daily-hunt-api.sh` runs this at the end of each morning's scan, so the site republishes daily. Instead of `wrangler login` you can put `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in `.env`.

The published site carries a simple visual privacy page (`/privacy`) and a methodology page (`/methodology`) generated straight from the source register, so it can never drift from what actually runs. Traffic is measured with cookieless [Cloudflare Web Analytics](https://www.cloudflare.com/web-analytics/): paste the Web Analytics token into `CF_BEACON_TOKEN` in `ui/index.html` to enable it, or leave it blank for no measurement at all.

## Command line

Run these with the venv Python (`.venv/bin/python scripts/summarize.py <cmd>`):

```
run             fetch feeds, then triage + write the daily digests
triage          select and summarize new feed candidates into the store
digest          write the daily digests (general + privacy/security/legal cuts)
synthesis       deep weekly synthesis; --lens privacy|security|legal, --days N, --max N
audit-sources   pressure-test source coverage: feed-health + gap analysis
lens            (re)score stored items on all three lenses + subtopics
```

`scripts/fetch_feeds.py` pulls the feeds on its own. `scripts/newsdb.py build` rebuilds the UI data and the methodology page from the store.

## Schedule it (optional)

To keep the store fresh without pressing buttons, add cron entries. The scripts load `.env` on their own, so cron sees your key.

```sh
crontab -e
```

```
7 7 * * *    /full/path/to/agent-privacy-news/scripts/daily-hunt-api.sh
41 7 * * 1   /full/path/to/agent-privacy-news/scripts/weekly-synthesis.sh
53 7 1 * *   /full/path/to/agent-privacy-news/scripts/audit-sources.sh
```

The first line runs a scan and republishes every morning. The Monday line writes the weekly privacy synthesis. The first-of-the-month line audits source coverage. Your machine has to be awake for a job to fire. Remove any line to stop that job.

## How it works

- `scripts/fetch_feeds.py` reads about 45 RSS/Atom feeds plus the arXiv and Hacker News APIs and drops anything already in the store. Most feeds are keyword-filtered for agentic-AI privacy and security; primary regulator and standards feeds skip that gate (set per feed in `data/sources.json` as `prefilter: loose|off`) and go straight to triage, since their wording rarely says "agent".
- `scripts/summarize.py` is the Claude pipeline. Triage uses structured JSON output so items always match the store format and only ever cite URLs from the feed pull. It refuses to invent stories or URLs. Every prose output follows a house style defined in the code.
- `scripts/newsdb.py` is the store: `ingest` merges new items and dedupes by URL, `build` regenerates the UI data and the public methodology page.
- `scripts/serve.py` (launched by `scripts/ui.sh`) is a localhost-only server that serves the UI and runs Scan and the on-demand syntheses behind the buttons.
- `data/sources.json` is the source register (question, tiers, inclusion and exclusion rules, and every feed). `data/items.json` is the deduped store. `data/digests/` and `data/reports/` hold the generated documents. The store outputs are git-ignored; each install builds its own.

## Cost and privacy

The only external calls are to the Anthropic API for summarization, plus the feed and paper fetches. Your key never leaves your machine except in the `x-api-key` header on those calls. The tool stores news, not personal data. The published site sets no cookies and builds no profile; its analytics are aggregate and cookieless. Claude declines to summarize some security content; the pipeline handles those declines with automatic fallbacks.

## The agentic variant (optional)

`scripts/daily-hunt.sh` runs an alternative daily hunt that drives the [Claude Code](https://claude.com/claude-code) CLI against `HUNT.md` instead of the API pipeline. It fetch-verifies every story and can search the web beyond the feeds, at higher cost and latency. It needs the `claude` CLI on your PATH. The API pipeline in `daily-hunt-api.sh` is the default.
