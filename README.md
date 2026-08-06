# agent-privacy-news

A self-updating tracker for privacy and security news in the agentic AI space. It covers attacks and data leakage through the tools agents use, Model Context Protocol (MCP) server vulnerabilities, agent-to-agent identity and authentication, and the wider cloud-platform and regulatory picture. It pulls from about 40 sources and uses Claude to pick and summarize the stories that matter. Each story is scored on three lenses (privacy, security, law) and tagged with security subtopics (prompt injection, supply chain, identity, and so on), so a privacy engineer, a security analyst, or a policy lead can each filter to what they care about. It serves a local web page with a daily digest, an on-demand delta report, and a deep weekly synthesis that reads each paper in full.

Nothing is hosted. It runs on your machine and writes plain files.

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

That prints a `http://127.0.0.1:<port>` address and opens it in your browser. On a first run the page is empty. Click **Scan now**. The tool pulls the feeds, has Claude select and summarize the relevant stories, scores them, and writes today's digest. A scan takes about a minute. Reload nothing; the page refreshes itself when the scan finishes.

Prefer the command line? This does the same work without the server:

```sh
.venv/bin/python scripts/summarize.py run
open ui/index.html      # macOS; or open the file in any browser
```

## The interface

The page has a news list, a digest panel, and a synthesis banner across the top.

**Scan now** pulls fresh news and summarizes it. The freshness pill next to it turns green under a day old, amber under three days, red beyond that.

**Lenses** (🔒 Privacy, 🛡 Security, ⚖ Law) each filter the list to stories that matter to that audience, rank them by relevance, and add a one-line note per story: which control it informs for privacy, which defense or threat for security, which obligation or risk for law. The lenses are multi-select. Turn on two and the list narrows to the cross-cutting stories, the ones relevant to both, ranked by combined relevance, with each lens's angle on the card. With the privacy lens on, the daily digest panel switches to its privacy-engineering view.

**Subtopic** chips filter by theme within three domains. Privacy covers data governance, PETs, consent, data minimization, deletion and erasure, and the rest. Security covers prompt injection, data exfiltration, supply chain, identity, sandbox escape, and so on. Legal covers the EU AI Act, GDPR, US state privacy law, FTC actions, liability, and more. Chips and card badges are color-coded by domain. The **Sort** control orders the list by newest, by importance, or grouped by subtopic. Grouping plus a lens gives a per-theme reading list ranked by relevance.

**📋 Report** opens a copy-paste report of only the privacy-eng stories that are new since the last time you ran it. Each run marks what it covered, so the next one shows only fresh deltas.

**🔬 Weekly synthesis** sits at the top as a standing panel. Press **Update** and it fetches each paper's full text, then writes a plain-language, mechanism-level briefing: the longer-term trends, a per-development breakdown of what it is and how it works and what it means for your roadmap, and a privacy-by-design gap map of what the industry shipped this window versus what is still missing. The panel shows the big picture by default with an expander for the full document and a copy button.

## Publish to the web (Cloudflare Pages)

The UI and its data hold no secrets, so you can publish a read-only copy for a team to browse. The published page shows the news, lenses, subtopics, digests, and the latest synthesis, but not the Scan, Report, or Update buttons, since those need the local server.

One-time, authenticate wrangler (opens a browser):

```sh
npx wrangler login
```

Then deploy or redeploy:

```sh
./scripts/deploy-cloudflare.sh
```

That rebuilds `ui/data.js` and pushes the `ui/` directory to a Cloudflare Pages project named `agent-privacy-news`. Cloudflare prints the public URL. Run the script again to refresh the site after a scan, or add it to the end of `scripts/daily-hunt-api.sh` so each morning's scan republishes. Instead of `wrangler login` you can put `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in `.env`.

## Command line

Run these with the venv Python (`.venv/bin/python scripts/summarize.py <cmd>`):

```
run         fetch feeds, then triage + write the daily digest
triage      select and summarize new feed candidates into the store
digest      write the daily digest (general + privacy-eng variants)
report      delta report of privacy-eng items new since the last report
synthesis   deep weekly synthesis; reads each paper (use --days N, --max N)
lens        (re)score the privacy-eng relevance of stored items
```

`scripts/fetch_feeds.py` pulls the feeds on its own. `scripts/newsdb.py build` rebuilds the UI data from the store.

## Schedule it (optional)

To keep the store fresh without pressing buttons, add cron entries. The scripts load `.env` on their own, so cron sees your key.

```sh
crontab -e
```

```
7 7 * * *   /full/path/to/agent-privacy-news/scripts/daily-hunt-api.sh
22 7 * * 1  /full/path/to/agent-privacy-news/scripts/weekly-report.sh
41 7 * * 1  /full/path/to/agent-privacy-news/scripts/weekly-synthesis.sh
```

The first line runs a scan every morning. The two Monday lines write a weekly report and a weekly synthesis. Your machine has to be awake for a job to fire. Remove any line to stop that job.

## How it works

- `scripts/fetch_feeds.py` reads about 40 RSS/Atom feeds plus the arXiv and Hacker News APIs, keyword-filters for agent privacy and security, and drops anything already in the store. Source list and rationale live in `SOURCES.md`.
- `scripts/summarize.py` is the Claude pipeline. Triage uses structured JSON output so items always match the store format and only ever cite URLs from the feed pull. It refuses to invent stories or URLs. Every prose output follows a house style defined in the code.
- `scripts/newsdb.py` is the store: `ingest` merges new items and dedupes by URL, `build` regenerates the data the UI reads.
- `scripts/serve.py` (launched by `scripts/ui.sh`) is a localhost-only server that serves the UI and runs Scan, Report, and Synthesis behind the buttons.
- `data/items.json` is the deduped store. `data/digests/` and `data/reports/` hold the generated documents. These are git-ignored; each install builds its own.

## Cost and privacy

The only external call is to the Anthropic API for summarization, plus the feed and paper fetches. Your key never leaves your machine except in the `x-api-key` header on those API calls. The tool stores news, not personal data. Claude declines to summarize some security content; the pipeline handles those declines with automatic fallbacks.

## The agentic variant (optional)

`scripts/daily-hunt.sh` runs an alternative daily hunt that drives the [Claude Code](https://claude.com/claude-code) CLI against `HUNT.md` instead of the API pipeline. It fetch-verifies every story and can search the web beyond the feeds, at higher cost and latency. It needs the `claude` CLI on your PATH. The API pipeline in `daily-hunt-api.sh` is the default.
