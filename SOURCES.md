# Source Strategy

Three tiers feed the daily hunt.

## Tier 1 — Automated feed pull (`scripts/fetch_feeds.py`)

43 feeds + 2 APIs, pulled concurrently (~10s), keyword-filtered to
(agent/MCP/A2A terms) AND (privacy/security/regulation terms), deduped
against the store → `data/feed-candidates.json`. Edit the `FEEDS` list in
the script to add/remove.

**Agent-security researchers & vendor research** — Embrace the Red (Johann
Rehberger — the best agent-exfiltration research), Simon Willison, Adversa AI,
Trail of Bits, Unit 42, Wiz, Snyk, Securelist, PromptArmor.

**Security press** — The Hacker News, BleepingComputer, Help Net Security,
SecurityWeek, GBHackers, Schneier, Dark Reading, The Record, 404 Media,
Risky Business News, The Register AI, Ars Technica AI.

**Privacy & regulatory** — EFF Deeplinks, EDPB news, EU Digital Strategy
(AI Act announcements at the source), FTC press releases, noyb, Future of
Privacy Forum, IAPP.

**Standards & protocol** — official MCP blog, MCP spec GitHub releases,
A2A GitHub releases, OWASP GenAI, Cloud Security Alliance.

**Cloud & model vendors** — AWS Security Blog, GCP Security Blog, OpenAI News.

**Newsletters** (web feeds) — Import AI, Latent Space, Don't Worry About the
Vase, Resilient Cyber.

**Community & academic** — r/netsec, Lobsters, Hacker News (Algolia API,
points-thresholded), arXiv cs.CR firehose + 4 targeted arXiv API queries.

## Tier 2 — Agentic web search

WebSearch/WebFetch in the daily hunt (per `HUNT.md`) for what feeds miss.
Known gaps to cover here, since these sources have **no working feed**:
Anthropic news/engineering, MSRC blog (malformed XML), NCC Group (malformed),
Invariant Labs (malformed), Zenity Labs, HiddenLayer, tl;dr sec, DWT AI Law
Advisor, Azure AI Foundry release notes, AWS Bedrock changelog.

## Tier 3 — Not yet automated (candidates for later)

- **Gmail newsletters** — subscribe to tl;dr sec, IAPP Daily Dashboard,
  Risky Biz newsletter; hunt reads them via the connected Gmail MCP tool.
- **Google Alerts → RSS** — free long-tail alerts ("MCP vulnerability",
  "agent data breach"), delivery = RSS, drop URLs into `FEEDS`.
- **NVD/CVE keyword API** — poll for CVEs matching MCP/agent keywords.
- **GitHub advisories** — `gh api /advisories` keyword-filtered.
- **Bluesky firehose** — open API, infosec community presence, no key needed.
- **Vendor changelog diffing** — WebFetch-and-compare for the no-feed pages
  listed in Tier 2.
