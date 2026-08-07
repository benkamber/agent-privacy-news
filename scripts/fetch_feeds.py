#!/usr/bin/env python3
"""Pull candidate stories from RSS/Atom feeds, arXiv, and Hacker News.

Writes keyword-filtered, recency-filtered candidates (minus URLs already in
data/items.json) to data/feed-candidates.json for the hunt agent to triage.
Stdlib only — no keys, no dependencies.

Usage: fetch_feeds.py [--days N]   (default 10)
"""
import concurrent.futures as cf
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_BUILTIN_FEEDS = [
    # agent-security researchers & vendor research teams
    ("Embrace the Red", "https://embracethered.com/blog/index.xml"),
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
    ("Adversa AI", "https://adversa.ai/feed/"),
    ("Trail of Bits", "https://blog.trailofbits.com/feed/"),
    ("Unit 42 (Palo Alto)", "https://unit42.paloaltonetworks.com/feed/"),
    ("Wiz Blog", "https://www.wiz.io/feed/rss.xml"),
    ("Snyk Blog", "https://snyk.io/blog/feed/"),
    ("Securelist (Kaspersky)", "https://securelist.com/feed/"),
    ("PromptArmor", "https://promptarmor.substack.com/feed"),
    # security press
    ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews"),
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
    ("Help Net Security", "https://www.helpnetsecurity.com/feed/"),
    ("SecurityWeek", "https://www.securityweek.com/feed/"),
    ("GBHackers", "https://gbhackers.com/feed/"),
    ("Schneier on Security", "https://www.schneier.com/feed/atom/"),
    ("Dark Reading", "https://www.darkreading.com/rss.xml"),
    ("The Record", "https://therecord.media/feed/"),
    ("404 Media", "https://www.404media.co/rss/"),
    ("Risky Business News", "https://risky.biz/rss.xml"),
    ("The Register AI", "https://www.theregister.com/software/ai_ml/headlines.atom"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
    # privacy & regulatory
    ("EFF Deeplinks", "https://www.eff.org/rss/updates.xml"),
    ("EDPB News", "https://www.edpb.europa.eu/feed/news_en"),
    ("EU Digital Strategy", "https://digital-strategy.ec.europa.eu/en/rss.xml"),
    ("FTC Press", "https://www.ftc.gov/feeds/press-release.xml"),
    ("noyb", "https://noyb.eu/en/rss.xml"),
    ("Future of Privacy Forum", "https://fpf.org/feed/"),
    ("IAPP", "https://iapp.org/rss"),
    # standards & protocol
    ("MCP Blog", "https://blog.modelcontextprotocol.io/index.xml"),
    ("MCP spec releases", "https://github.com/modelcontextprotocol/modelcontextprotocol/releases.atom"),
    ("A2A releases", "https://github.com/a2aproject/A2A/releases.atom"),
    ("OWASP GenAI", "https://genai.owasp.org/feed/"),
    ("Cloud Security Alliance", "https://cloudsecurityalliance.org/blog/feed"),
    # cloud & model vendors
    ("AWS Security Blog", "https://aws.amazon.com/blogs/security/feed/"),
    ("GCP Security Blog", "https://cloudblog.withgoogle.com/products/identity-security/rss/"),
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    # newsletters
    ("Import AI", "https://importai.substack.com/feed"),
    ("Latent Space", "https://www.latent.space/feed"),
    ("Don't Worry About the Vase", "https://thezvi.substack.com/feed"),
    ("Resilient Cyber", "https://www.resilientcyber.io/feed"),
    # community
    ("r/netsec", "https://www.reddit.com/r/netsec/.rss"),
    ("Lobsters", "https://lobste.rs/rss"),
    # academic firehose
    ("arXiv cs.CR", "https://rss.arxiv.org/rss/cs.CR"),
]


# Prefilter modes per feed (the `prefilter` field in sources.json):
#   both  (default): keep an item only if it matches an AGENT term AND a RISK term.
#   loose: keep on a RISK term alone. For primary regulator/standards feeds whose
#          items rarely say "agent" ("general-purpose AI", "automated decision");
#          triage makes the final agentic-relevance call.
#   off  : no keyword gate. For low-volume release/spec atoms where every item counts.
_MODES = ("both", "loose", "off")


def _load_feeds():
    """Prefer the source register (data/sources.json); fall back to the built-in list.
    Returns (name, url, prefilter_mode) tuples."""
    reg = ROOT / "data" / "sources.json"
    try:
        feeds = []
        for f in json.loads(reg.read_text()).get("feeds", []):
            if not f.get("url"):
                continue
            mode = f.get("prefilter", "both")
            feeds.append((f["name"], f["url"], mode if mode in _MODES else "both"))
        if feeds:
            return feeds
    except Exception as e:
        print(f"  sources.json unreadable ({e}); using built-in feed list")
    return [(n, u, "both") for (n, u) in _BUILTIN_FEEDS]


FEEDS = _load_feeds()

ARXIV_QUERIES = [
    'all:"LLM agent" AND all:"privacy"',
    'all:"model context protocol"',
    'all:"prompt injection"',
    'all:"multi-agent" AND all:"security"',
]

HN_QUERIES = ["MCP security", "agent privacy", "prompt injection", "AI agent security"]

# candidate must match (AGENT terms) AND (RISK terms), except for loose/off feeds
AGENT_RE = re.compile(
    r"\b(agent|agentic|mcp|model context protocol|a2a|copilot|claude|gpt|llm|"
    r"assistant|tool.?call|tool use|function.?call|autonomous ai|computer.?use|"
    r"general.purpose ai|gpai|automated decision|ai system|ai model|"
    r"foundation model|frontier model)\b", re.I)
RISK_RE = re.compile(
    r"\b(privac|security|vulnerab|exploit|inject|exfiltrat|leak|breach|cve|"
    r"credential|consent|gdpr|ai act|compliance|residency|sovereign|identity|"
    r"auth|permission|sandbox|governance|audit|surveill)\w*", re.I)


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "agent-privacy-news/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def strip_ns(tag):
    return tag.split("}")[-1]


def parse_date(s):
    if not s:
        return None
    for fn in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            d = fn(s.strip().replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def parse_feed(xml_bytes):
    """Yield (title, link, date, blurb) from RSS2 or Atom."""
    root = ET.fromstring(xml_bytes)
    for entry in root.iter():
        if strip_ns(entry.tag) not in ("item", "entry"):
            continue
        title = link = blurb = date = None
        for c in entry:
            t = strip_ns(c.tag)
            if t == "title":
                title = (c.text or "").strip()
            elif t == "link":
                link = (c.text or "").strip() or c.get("href")
            elif t in ("description", "summary", "abstract"):
                blurb = re.sub(r"<[^>]+>", " ", c.text or "")[:400]
            elif t in ("pubDate", "published", "updated", "date"):
                date = date or parse_date(c.text)
        if title and link:
            yield title, link, date, blurb or ""


def collect():
    days = 10
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    known = set()
    items_file = ROOT / "data" / "items.json"
    if items_file.exists():
        known = {i["url"].rstrip("/") for i in json.loads(items_file.read_text())}

    candidates, errors = [], []

    def add(source, title, link, date, blurb, mode="both"):
        if link.rstrip("/") in known:
            return
        if date and date < cutoff:
            return
        text = f"{title} {blurb}"
        if mode == "both" and not (AGENT_RE.search(text) and RISK_RE.search(text)):
            return
        if mode == "loose" and not RISK_RE.search(text):
            return
        # mode == "off": no keyword gate; recency + dedupe still apply.
        candidates.append({
            "source": source,
            "title": title,
            "url": link,
            "published": date.date().isoformat() if date else None,
            "blurb": blurb.strip(),
        })

    def pull(feed):
        name, url, mode = feed
        return name, mode, list(parse_feed(get(url)))

    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(pull, f): f[0] for f in FEEDS}
        for fut in cf.as_completed(futures):
            try:
                name, mode, entries = fut.result()
                for title, link, date, blurb in entries:
                    add(name, title, link, date, blurb, mode)
            except Exception as e:
                errors.append(f"{futures[fut]}: {type(e).__name__}: {e}")

    for q in ARXIV_QUERIES:
        try:
            u = ("http://export.arxiv.org/api/query?search_query="
                 + urllib.parse.quote(q)
                 + "&sortBy=submittedDate&sortOrder=descending&max_results=15")
            for title, link, date, blurb in parse_feed(get(u)):
                add("arXiv API", re.sub(r"\s+", " ", title), link, date, blurb)
        except Exception as e:
            errors.append(f"arXiv [{q}]: {type(e).__name__}: {e}")

    since = int(cutoff.timestamp())
    for q in HN_QUERIES:
        try:
            u = ("https://hn.algolia.com/api/v1/search_by_date?tags=story"
                 f"&numericFilters=created_at_i>{since},points>5&hitsPerPage=20"
                 "&query=" + urllib.parse.quote(q))
            for hit in json.loads(get(u))["hits"]:
                link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
                add(f"Hacker News ({hit.get('points', 0)} pts)", hit.get("title", ""),
                    link, parse_date(hit.get("created_at")), "")
        except Exception as e:
            errors.append(f"HN [{q}]: {type(e).__name__}: {e}")

    # dedupe by URL, keep first (feed order = curated order)
    seen, unique = set(), []
    for c in candidates:
        k = c["url"].rstrip("/")
        if k not in seen:
            seen.add(k)
            unique.append(c)

    out = ROOT / "data" / "feed-candidates.json"
    out.write_text(json.dumps(
        {"fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "window_days": days, "errors": errors, "candidates": unique},
        indent=1) + "\n")
    print(f"{len(unique)} candidates written to {out.relative_to(ROOT)} "
          f"({len(errors)} source errors)")
    for e in errors:
        print("  feed error:", e)


if __name__ == "__main__":
    collect()
