#!/usr/bin/env python3
"""News store for agent-privacy-news.

Commands:
  ingest <file.json>  Merge a JSON array of new items into data/items.json
                      (dedupes by normalized URL), then rebuild ui/data.js.
  build               Rebuild ui/data.js from data/items.json + data/digests/.
"""
import hashlib
import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
DIGESTS = ROOT / "data" / "digests"
DATA_JS = ROOT / "ui" / "data.js"
SOURCES = ROOT / "data" / "sources.json"
METHODOLOGY_HTML = ROOT / "ui" / "methodology.html"

TAGS = {"tools", "mcp", "a2a", "polycloud", "regulation", "incident", "research", "product"}

# Subtopic taxonomies (keep in sync with summarize.py and the UI).
SUBTOPICS = {"prompt-injection", "data-exfiltration", "supply-chain",
             "identity-auth", "sandbox-escape", "memory-poisoning",
             "vulnerability", "red-teaming", "detection-response",
             "governance", "model-security"}
PE_SUBTOPICS = {"data-governance", "pets", "consent", "data-minimization",
                "deletion-erasure", "de-identification", "data-residency",
                "differential-privacy", "access-portability", "purpose-limitation"}
LAW_SUBTOPICS = {"eu-ai-act", "gdpr", "us-state-privacy", "ftc", "liability",
                 "cross-border-transfer", "sector-regulation", "litigation",
                 "standards", "disclosure-duty"}


def _score(v):
    """Clamp a 0-3 lens score, or None if not yet classified."""
    return max(0, min(3, int(v))) if v is not None else None


def norm_url(url: str) -> str:
    u = url.strip().rstrip("/")
    u = u.replace("http://", "https://")
    return u.split("#")[0].split("?utm_")[0]


def item_id(url: str) -> str:
    return hashlib.sha1(norm_url(url).encode()).hexdigest()[:12]


def load_items() -> list:
    if ITEMS.exists():
        return json.loads(ITEMS.read_text())
    return []


def ingest(path: str) -> None:
    new = json.loads(Path(path).read_text())
    items = load_items()
    seen = {i["id"] for i in items}
    added = skipped = 0
    for it in new:
        iid = item_id(it["url"])
        if iid in seen:
            skipped += 1
            continue
        tags = [t for t in it.get("tags", []) if t in TAGS] or ["tools"]
        pe = it.get("pe_score")
        items.append({
            "id": iid,
            "title": it["title"].strip(),
            "url": it["url"].strip(),
            "source": it.get("source", "").strip(),
            "published": it.get("published"),
            "fetched": datetime.now().isoformat(timespec="minutes"),
            "tags": tags,
            "summary": it.get("summary", "").strip(),
            "privacy_angle": it.get("privacy_angle", "").strip(),
            "importance": max(1, min(5, int(it.get("importance", 3)))),
            # three audience lenses, each 0-3 (None = not yet classified;
            # backfill via summarize.py lens). privacy / security / law.
            "pe_score": _score(pe),
            "pe_angle": (it.get("pe_angle") or "").strip(),
            "sec_score": _score(it.get("sec_score")),
            "sec_angle": (it.get("sec_angle") or "").strip(),
            "law_score": _score(it.get("law_score")),
            "law_angle": (it.get("law_angle") or "").strip(),
            # subtopics for theme sorting: security, privacy, legal.
            "subtopics": [t for t in it.get("subtopics", []) if t in SUBTOPICS],
            "pe_subtopics": [t for t in it.get("pe_subtopics", []) if t in PE_SUBTOPICS],
            "law_subtopics": [t for t in it.get("law_subtopics", []) if t in LAW_SUBTOPICS],
            # delta tracking for the privacy-eng report: True once an item has
            # been included in a generated report.
            "reported": bool(it.get("reported", False)),
        })
        seen.add(iid)
        added += 1
    items.sort(key=lambda i: (i.get("published") or i["fetched"]), reverse=True)
    ITEMS.write_text(json.dumps(items, indent=2) + "\n")
    print(f"ingested: {added} added, {skipped} duplicates skipped, {len(items)} total")
    build()


def _dom_badges(domains: list) -> str:
    label = {"security": "security", "privacy": "privacy", "law": "legal"}
    return "".join(
        f'<span class="dom {d}">{label.get(d, html.escape(str(d)))}</span>'
        for d in domains)


def _feed_row(f: dict) -> str:
    name = html.escape(f.get("name", ""))
    url = html.escape(f.get("url", "") or "", quote=True)
    note = html.escape(f.get("note", "") or "")
    title = f'<a href="{url}" target="_blank" rel="noopener">{name}</a>' if url else name
    return (f'<li><div class="fn">{title} {_dom_badges(f.get("domains", []))}</div>'
            f'<div class="fnote">{note}</div></li>')


def _build_methodology_page() -> None:
    """Generate ui/methodology.html from data/sources.json so the public
    methodology page always matches the live register. Best-effort: a missing or
    malformed register skips the page and never breaks the rest of the build."""
    try:
        reg = json.loads(SOURCES.read_text())
    except Exception as e:
        print(f"  methodology page skipped (sources.json unreadable: {e})")
        return
    m = reg.get("methodology", {})
    feeds = reg.get("feeds", [])
    apis = reg.get("apis", [])
    tiers = m.get("tiers", {})
    esc = html.escape

    tier_labels = {"primary": "Primary", "secondary": "Secondary", "tertiary": "Tertiary"}
    tier_cards = "".join(
        f'<div class="card"><h3>{tier_labels[t]}</h3><p>{esc(tiers.get(t, ""))}</p></div>'
        for t in ("primary", "secondary", "tertiary") if tiers.get(t))

    def li_list(xs):
        return "".join(f"<li>{esc(x)}</li>" for x in xs)

    # feeds grouped by tier, then the query-based APIs
    groups = ""
    for t in ("primary", "secondary", "tertiary"):
        fs = [f for f in feeds if f.get("tier") == t]
        if not fs:
            continue
        rows = "".join(_feed_row(f) for f in sorted(fs, key=lambda x: x.get("name", "").lower()))
        groups += (f'<h3 class="tier">{tier_labels[t]} '
                   f'<span class="cnt">{len(fs)}</span></h3><ul class="feeds">{rows}</ul>')
    if apis:
        rows = "".join(
            f'<li><div class="fn">{esc(a.get("name", ""))} '
            f'{_dom_badges(a.get("domains", []))} <span class="cnt">{esc(a.get("tier", ""))}</span></div>'
            f'<div class="fnote">{esc(a.get("note", ""))}</div></li>' for a in apis)
        groups += f'<h3 class="tier">Query APIs <span class="cnt">{len(apis)}</span></h3><ul class="feeds">{rows}</ul>'

    total = len([f for f in feeds if f.get("url")]) + len(apis)
    updated = max([f.get("last_reviewed", "") for f in feeds] or [""]) or date.today().isoformat()
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Methodology · Agent Privacy &amp; Security News</title>
<style>
  :root {{
    --bg: #f7f7f5; --panel: #ffffff; --ink: #1a1a1a; --muted: #6b6b66;
    --line: #e4e4df; --accent: #7c5cff; --sec: #cc6a2b; --law: #2f8f83;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #16161a; --panel: #1f1f25; --ink: #ebebe6; --muted: #9a9a94;
      --line: #2e2e35; --accent: #9d85ff; --sec: #e08a4e; --law: #4fb3a6;
    }}
  }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ background: var(--bg); color: var(--ink);
         font: 16px/1.6 -apple-system, "Segoe UI", system-ui, sans-serif; }}
  .wrap {{ max-width: 820px; margin: 0 auto; padding: 40px 24px 80px; }}
  a {{ color: var(--accent); }}
  .back {{ font-size: 14px; color: var(--muted); text-decoration: none; }}
  h1 {{ font-size: 32px; letter-spacing: -0.02em; margin: 18px 0 6px; }}
  .lead {{ font-size: 18px; color: var(--muted); margin-bottom: 8px; }}
  .updated {{ font-size: 13px; color: var(--muted); margin-bottom: 32px; }}
  .cards {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; margin: 12px 0 32px; }}
  @media (max-width: 640px) {{ .cards {{ grid-template-columns: 1fr; }} }}
  .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
          padding: 16px 18px; }}
  .card h3 {{ font-size: 15px; margin-bottom: 6px; }}
  .card p {{ font-size: 13px; color: var(--muted); }}
  section {{ margin-bottom: 30px; }}
  section h2 {{ font-size: 20px; margin-bottom: 10px; }}
  section > p {{ margin-bottom: 10px; }}
  ul.plain {{ padding-left: 20px; }} ul.plain li {{ margin-bottom: 4px; }}
  h3.tier {{ font-size: 15px; margin: 22px 0 8px; text-transform: uppercase;
            letter-spacing: 0.04em; color: var(--muted); }}
  .cnt {{ font-size: 12px; color: var(--muted); border: 1px solid var(--line);
         border-radius: 20px; padding: 1px 8px; margin-left: 4px; }}
  ul.feeds {{ list-style: none; padding: 0; display: grid; gap: 10px; }}
  ul.feeds li {{ background: var(--panel); border: 1px solid var(--line);
                border-radius: 12px; padding: 12px 14px; }}
  .fn {{ font-size: 15px; font-weight: 600; }}
  .fn a {{ text-decoration: none; }}
  .fnote {{ font-size: 13px; color: var(--muted); margin-top: 2px; }}
  .dom {{ font-size: 11px; font-weight: 600; border-radius: 20px; padding: 1px 8px;
         margin-left: 4px; vertical-align: middle; }}
  .dom.security {{ color: #fff; background: var(--sec); }}
  .dom.privacy {{ color: #fff; background: var(--accent); }}
  .dom.law {{ color: #fff; background: var(--law); }}
  .foot {{ font-size: 13px; color: var(--muted); border-top: 1px solid var(--line);
          padding-top: 20px; margin-top: 8px; }}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="./">&larr; Back to the news</a>
  <h1>How this is built</h1>
  <p class="lead">{esc(m.get("question", ""))}</p>
  <p class="updated">Register last reviewed {esc(updated)} · {total} sources</p>

  <section>
    <h2>How sources are weighted</h2>
    <p>Every source sits in one of three tiers. A claim rests on primary sources; the rest widen what gets seen and help confirm a story.</p>
    <div class="cards">{tier_cards}</div>
  </section>

  <section>
    <h2>What gets in</h2>
    <ul class="plain">{li_list(m.get("inclusion", []))}</ul>
  </section>

  <section>
    <h2>What stays out</h2>
    <ul class="plain">{li_list(m.get("exclusion", []))}</ul>
  </section>

  <section>
    <h2>The sources</h2>
    <p>The full register, kept in the open. Each daily run reads these feeds plus the query APIs below, then an AI pass selects and summarizes what is genuinely new. Most feeds are keyword-filtered first for agentic-AI privacy, security, and legal relevance. Primary regulator and standards feeds skip that gate and go straight to the AI pass, since their wording rarely says "agent".</p>
    {groups}
  </section>

  <section>
    <h2>Keeping it honest</h2>
    <p>{esc(m.get("review_cadence", ""))}</p>
    <p>The register lives in version control as <a href="https://github.com/benkamber/agent-privacy-news/blob/main/data/sources.json" target="_blank" rel="noopener">data/sources.json</a>. This page is generated straight from it, so it cannot drift from what actually runs.</p>
  </section>

  <p class="foot">Open source at
    <a href="https://github.com/benkamber/agent-privacy-news" target="_blank" rel="noopener">github.com/benkamber/agent-privacy-news</a>.
    See also the <a href="privacy.html">privacy page</a>.</p>
</div>
</body>
</html>
"""
    METHODOLOGY_HTML.write_text(page)
    print(f"built ui/methodology.html: {total} sources")


def build() -> None:
    items = load_items()
    digests = []
    if DIGESTS.exists():
        # general digests are YYYY-MM-DD.md; the per-lens variants, if present,
        # are YYYY-MM-DD.{pe,sec,law}.md and ride along on the same entry.
        variants = (("pe", "pe_markdown"), ("sec", "sec_markdown"), ("law", "law_markdown"))
        suffixes = tuple(f".{s}.md" for s, _ in variants)
        general = sorted((f for f in DIGESTS.glob("*.md") if not f.name.endswith(suffixes)),
                         reverse=True)
        for f in general:
            entry = {"date": f.stem, "markdown": f.read_text()}
            for suf, key in variants:
                v = DIGESTS / f"{f.stem}.{suf}.md"
                if v.exists():
                    entry[key] = v.read_text()
            digests.append(entry)
    # Per-lens weekly syntheses. Privacy runs on the weekly cron; security and
    # legal are generated on demand. Keyed by lens so the UI panel can tab across.
    synth = {}
    for lens, fname in (("privacy", "latest-synthesis.md"),
                        ("security", "latest-synthesis.sec.md"),
                        ("legal", "latest-synthesis.law.md")):
        p = ROOT / "data" / "reports" / fname
        if p.exists():
            synth[lens] = {
                "markdown": p.read_text(),
                "generated": datetime.fromtimestamp(
                    p.stat().st_mtime).isoformat(timespec="seconds"),
            }
    synth = synth or None
    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "items": items,
        "digests": digests,
        "synthesis": synth,
    }
    DATA_JS.parent.mkdir(parents=True, exist_ok=True)
    DATA_JS.write_text("window.NEWS_DATA = " + json.dumps(payload, indent=1) + ";\n")
    print(f"built ui/data.js: {len(items)} items, {len(digests)} digests")
    _build_methodology_page()


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"ingest", "build"}:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "ingest":
        if len(sys.argv) != 3:
            sys.exit("usage: newsdb.py ingest <file.json>")
        ingest(sys.argv[2])
    else:
        build()


if __name__ == "__main__":
    main()
