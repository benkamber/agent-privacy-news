# Daily Hunt Playbook, Agent Privacy News

You are running the daily privacy-news hunt for this project. Work from the
project root (the repository directory). Follow these steps exactly.

## Mission

Find news published in the **last ~7 days** (use today's real date) about
**privacy and security in agentic AI**, across three lenses:

1. **agent ↔ tools** — prompt injection / data exfiltration through tool use,
   tool permission models, sandboxing, consent UX, credential leakage.
2. **agent ↔ MCP** — MCP server vulnerabilities, malicious/typosquatted
   servers, registries and signing, MCP governance in enterprises.
3. **agent ↔ agent & polycloud** — A2A protocol, agent identity/auth
   (OAuth-for-agents, IETF/OpenID work), multi-agent security research,
   agentic browsers; plus agent platforms across AWS/Azure/GCP/Anthropic/
   OpenAI (data residency, cross-cloud data flows, trace/telemetry privacy),
   regulation (EU AI Act, GDPR/DPA guidance, FTC), and enterprise agent
   governance/DLP products and incidents.

## Steps

1. Read `data/items.json` (titles + URLs only) so you know what's already
   covered. Do not re-add stories already in the store; a *material update*
   to a known story is a new item.
2. Run `python3 scripts/fetch_feeds.py` — it pulls 14 curated RSS/Atom feeds,
   the arXiv API, and Hacker News (see `SOURCES.md`), keyword-filters them,
   and writes `data/feed-candidates.json`. Read the candidates and triage:
   WebFetch the promising ones to verify and assess. This is your primary
   source; note any feed errors it reports.
3. Then run **at least 2 WebSearch queries per lens** (6+ total) to catch
   stories the feeds missed, varying phrasing
   and including the current month/year in some queries. Use WebFetch on
   promising hits to verify the article exists, its real publication date,
   and what it actually says.
4. Keep only items that are genuinely about privacy/security/compliance in
   agentic AI and ≤ ~7 days old (≤ 30 days if the day is thin). Aim for
   3–10 new items; zero is acceptable on a quiet day.
5. Write the new items to a temp file (e.g. `/tmp/new-items.json` or the
   scratchpad) as a JSON array with this exact shape per item:

   ```json
   {
     "title": "...",
     "url": "https://... (real, fetched URL)",
     "source": "Publication name",
     "published": "YYYY-MM-DD or null",
     "tags": ["tools" | "mcp" | "a2a" | "polycloud" | "regulation" | "incident" | "research" | "product"],
     "summary": "2–3 factual sentences.",
     "privacy_angle": "1 sentence: why this matters for privacy in agentic AI.",
     "importance": 1-5
   }
   ```

6. Ingest and dedupe: `python3 scripts/newsdb.py ingest <temp-file>`
   (it skips URLs already in the store and rebuilds the UI data).
7. Write the daily digest to `data/digests/YYYY-MM-DD.md` (today's date):
   - Title line: `# Daily Digest — YYYY-MM-DD`
   - A 2–4 sentence **TL;DR** paragraph of the day's picture.
   - A **Top stories** section: the day's items ordered by importance, each
     as `**[Title](url)** (Source, date, tags)` followed by summary +
     privacy angle.
   - If nothing new: say so and note anything still developing.
8. Rebuild UI data: `python3 scripts/newsdb.py build`
9. Finish with a one-paragraph report of how many items were found/added,
   including any feed sources that errored.

## Rules

- Never fabricate URLs, dates, or stories — every item must come from a page
  you actually fetched.
- Only edit files inside this project (plus your temp file).
- Importance calibration: 5 = major breach/regulatory action, 4 = significant
  vuln or platform policy change, 3 = notable research/product news,
  2 = incremental, 1 = minor.
