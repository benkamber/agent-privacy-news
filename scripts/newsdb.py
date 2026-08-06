#!/usr/bin/env python3
"""News store for agent-privacy-news.

Commands:
  ingest <file.json>  Merge a JSON array of new items into data/items.json
                      (dedupes by normalized URL), then rebuild ui/data.js.
  build               Rebuild ui/data.js from data/items.json + data/digests/.
"""
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
DIGESTS = ROOT / "data" / "digests"
DATA_JS = ROOT / "ui" / "data.js"

TAGS = {"tools", "mcp", "a2a", "polycloud", "regulation", "incident", "research", "product"}


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
            "fetched": date.today().isoformat(),
            "tags": tags,
            "summary": it.get("summary", "").strip(),
            "privacy_angle": it.get("privacy_angle", "").strip(),
            "importance": max(1, min(5, int(it.get("importance", 3)))),
            # privacy-engineer lens: 0-3 relevance for building agentic privacy
            # capabilities (None = not yet classified; backfill via summarize.py lens)
            "pe_score": (max(0, min(3, int(pe))) if pe is not None else None),
            "pe_angle": (it.get("pe_angle") or "").strip(),
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


def build() -> None:
    items = load_items()
    digests = []
    if DIGESTS.exists():
        # general digests are YYYY-MM-DD.md; the privacy-eng variant, if present,
        # is YYYY-MM-DD.pe.md and rides along on the same entry.
        general = sorted((f for f in DIGESTS.glob("*.md") if not f.name.endswith(".pe.md")),
                         reverse=True)
        for f in general:
            entry = {"date": f.stem, "markdown": f.read_text()}
            pe = DIGESTS / f"{f.stem}.pe.md"
            if pe.exists():
                entry["pe_markdown"] = pe.read_text()
            digests.append(entry)
    synth = None
    syn_file = ROOT / "data" / "reports" / "latest-synthesis.md"
    if syn_file.exists():
        synth = {
            "markdown": syn_file.read_text(),
            "generated": datetime.fromtimestamp(
                syn_file.stat().st_mtime).isoformat(timespec="seconds"),
        }
    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "items": items,
        "digests": digests,
        "synthesis": synth,
    }
    DATA_JS.parent.mkdir(parents=True, exist_ok=True)
    DATA_JS.write_text("window.NEWS_DATA = " + json.dumps(payload, indent=1) + ";\n")
    print(f"built ui/data.js: {len(items)} items, {len(digests)} digests")


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
