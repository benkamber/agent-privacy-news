#!/usr/bin/env python3
"""Aggregate and summarize privacy-news research using Claude via the API.

Subcommands (run with the project venv: .venv/bin/python scripts/summarize.py ...):
  triage   Read data/feed-candidates.json, have Claude select and summarize the
           genuinely relevant stories into store-ready items, then ingest them
           (dedupe by URL) into data/items.json.
  digest   Have Claude write the daily digest from recently added items to
           data/digests/YYYY-MM-DD.md and rebuild ui/data.js.
  run      triage then digest — the full API pipeline.

Auth: set ANTHROPIC_API_KEY in the environment (or use `ant auth login`).
Model: claude-opus-5 ($5/$25 per MTok). A typical daily run costs a few cents.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
import newsdb  # noqa: E402  (ingest/build helpers)

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-opus-5"
BETAS = ["server-side-fallback-2026-07-01"]
PRICE_IN, PRICE_OUT = 5.00, 25.00  # $ per MTok

TAGS = ["tools", "mcp", "a2a", "polycloud", "regulation", "incident", "research", "product"]

# Security subtopics: a theme axis for the security community to sort by. An item
# carries 1-3. Keep this list in sync with SUBTOPICS in newsdb.py and the UI.
SUBTOPICS = ["prompt-injection", "data-exfiltration", "supply-chain",
             "identity-auth", "sandbox-escape", "memory-poisoning",
             "vulnerability", "red-teaming", "detection-response",
             "governance", "model-security"]

SUBTOPIC_DEF = """\
Security subtopics (`subtopics`): assign 1-3 per item from this set so the
security community can sort by theme. Pick the ones that genuinely fit; do not
force all.
  prompt-injection: direct or indirect injection, including data/agent injection.
  data-exfiltration: leakage of user data, credentials, or secrets.
  supply-chain: poisoned packages, malicious or typosquatted MCP servers, deps.
  identity-auth: agent identity, authn/z, delegation, impersonation, spoofing.
  sandbox-escape: isolation failure, RCE, container or VM escape.
  memory-poisoning: attacks on an agent's persistent memory or state.
  vulnerability: a disclosed CVE or concrete flaw in a product or tool.
  red-teaming: offensive testing, benchmarks, evals, attack frameworks.
  detection-response: defensive tooling, monitoring, DLP, SIEM, guardrails.
  governance: policy, compliance, regulation, audit, standards.
  model-security: model-level attacks such as jailbreak, backdoor, or poisoning."""

PE_SUBTOPICS = ["data-governance", "pets", "consent", "data-minimization",
                "deletion-erasure", "de-identification", "data-residency",
                "differential-privacy", "access-portability", "purpose-limitation"]

PE_SUBTOPIC_DEF = """\
Privacy subtopics (`pe_subtopics`): assign 0-3 that fit; empty array if none.
  data-governance: policy, cataloging, ownership, and lifecycle of data.
  pets: privacy-enhancing tech (encryption in use, federated learning, enclaves, MPC).
  consent: consent capture, granularity, revocation.
  data-minimization: collecting or retaining less data.
  deletion-erasure: deleting data on request, including logs, memory, training sets.
  de-identification: anonymization, pseudonymization, redaction.
  data-residency: where data is stored or processed, sovereignty.
  differential-privacy: DP mechanisms and budgets.
  access-portability: data-subject access and export.
  purpose-limitation: binding data use to a stated purpose."""

LAW_SUBTOPICS = ["eu-ai-act", "gdpr", "us-state-privacy", "ftc", "liability",
                 "cross-border-transfer", "sector-regulation", "litigation",
                 "standards", "disclosure-duty"]

LAW_SUBTOPIC_DEF = """\
Legal subtopics (`law_subtopics`): assign 0-3 that fit; empty array if none.
  eu-ai-act: the EU AI Act, its obligations and enforcement.
  gdpr: GDPR and EU data protection.
  us-state-privacy: CCPA, CPRA, and other US state privacy law.
  ftc: FTC actions, guidance, US federal enforcement.
  liability: who is responsible when an agent causes harm.
  cross-border-transfer: international data-transfer rules.
  sector-regulation: HIPAA, financial, and other sector rules.
  litigation: lawsuits, rulings, court decisions.
  standards: NIST, ISO, and formal standards or frameworks.
  disclosure-duty: transparency, labeling, and notice obligations."""

MISSION = """\
You are the aggregation engine for a privacy-news tracker focused on agentic AI.
Coverage has three lenses:
1. agent<->tools: prompt injection / data exfiltration through tool use, tool
   permission models, sandboxing, consent UX, credential leakage.
2. agent<->MCP: MCP server vulnerabilities, malicious servers, registries and
   signing, MCP governance in enterprises.
3. agent<->agent & polycloud: A2A protocol, agent identity/auth, multi-agent
   security research, agentic browsers; agent platforms across
   AWS/Azure/GCP/Anthropic/OpenAI (data residency, cross-cloud data flows),
   regulation (EU AI Act, GDPR, FTC), enterprise agent governance and incidents.

Importance calibration: 5 = major breach/regulatory action, 4 = significant
vuln or platform policy change, 3 = notable research/product news,
2 = incremental, 1 = minor."""

# The "privacy-engineer lens" — a second axis, orthogonal to importance and to
# the topical tags. It scores how useful a story is to a privacy engineer who is
# BUILDING privacy capabilities into agentic systems.
LENS_DEF = """\
The privacy-engineer lens (`pe_score`, 0-3) rates how relevant a story is to a
privacy engineer building privacy capabilities for agentic AI — someone
implementing controls such as consent/permission UX, data minimization, PII
redaction, memory and identity isolation, differential privacy, scoped
credentials, data residency, deletion/erasure (GDPR), agent authentication, or
DLP/governance and audit.
  3 = directly informs building or designing such a capability/control (a
      technique, standard, primitive, regulation to implement against, or a
      failure that dictates a specific control).
  2 = clearly relevant context for that work.
  1 = tangential.
  0 = not relevant to building privacy capabilities (e.g. a pure attack or
      breach story with no reusable control lesson).
`pe_angle`: one short sentence naming the capability/control the story informs
(empty string when pe_score is 0 or 1)."""

SEC_LENS_DEF = """\
The security lens (`sec_score`, 0-3) rates how useful a story is to a security
engineer or analyst securing agentic systems: threat detection, vulnerability
management, attack techniques to defend against, red-teaming, hardening, secure
architecture, and incident response.
  3 = directly informs a detection, defense, or hardening decision (a technique,
      a flaw to patch, an attack to detect, a control to deploy).
  2 = clearly relevant security context.
  1 = tangential.
  0 = not a security story.
`sec_angle`: one short sentence on the defensive action or threat it informs
(empty string when sec_score is 0 or 1)."""

LAW_LENS_DEF = """\
The law lens (`law_score`, 0-3) rates how relevant a story is to a legal,
policy, or compliance professional tracking agentic AI: regulation and
enforcement (EU AI Act, GDPR, FTC, state law), liability, disclosure and
transparency duties, standards, contracts and DPAs, and legal risk.
  3 = a law, enforcement action, ruling, or duty to comply with or advise on.
  2 = clearly relevant legal or policy context.
  1 = tangential.
  0 = no legal or regulatory angle.
`law_angle`: one short sentence on the obligation, risk, or development it
raises (empty string when law_score is 0 or 1)."""

# Condensed rubric from a privacy-review framework (Hoepman's 8 privacy-by-design
# strategies + data-subject rights), used to structure the weekly synthesis into
# a "what shipped vs. what's still missing" gap map.
GUARDIAN_RUBRIC = """\
Privacy-by-Design gap-map lens. Evaluate the window's developments against
Hoepman's 8 privacy strategies and data-subject rights, asking for EACH: what
did the industry actually ship this window, and what is still missing (where
solutions are needed)?
  - MINIMIZE: collect only what is strictly necessary.
  - HIDE: encrypt / hash / anonymize to limit exposure.
  - SEPARATE: isolate processing contexts to prevent correlation.
  - AGGREGATE: prefer aggregate data over individual records.
  - INFORM: tell users what is collected, why, and who sees it.
  - CONTROL: give users meaningful, revocable control over their data.
  - ENFORCE: technical measures that guarantee the policy (not prompts or UX).
  - DEMONSTRATE: prove compliance via audit logs and records of processing.
  - DATA-SUBJECT RIGHTS: access, deletion (including logs, agent memory, and
    training sets), portability, objection.
"Would The Guardian veto it?" = patterns a privacy team should refuse to adopt:
collecting just-in-case, consent theater, guardrails that can't be enforced,
agent memory with no deletion path, PII in logs/traces."""

# Prose contract applied to every summary, digest, report, and synthesis the
# tool writes. The requested markdown structure (headings, bulleted items,
# labeled fields) is a task instruction and stays; these rules govern the prose
# inside it.
PROSE_DIRECTIVE = """\
PROSE DIRECTIVE. Follow this in all prose you write here.

Goal: prose a careful reader cannot flag as machine-written. Write like a smart
colleague who knows the subject cold, typing fast to a peer. Plain, direct,
concrete. Internal-memo register, not published essay: no marketing or
motivational tone, no performed excitement, no exclamation marks unless quoting
one.

Diction: prefer short Anglo-Saxon verbs. use (not leverage/utilize), show (not
demonstrate/underscore/highlight), cut (not mitigate), help (not facilitate),
end (not conclude), make sure (not ensure), is (not serves as/acts as), has
(not boasts/comprises), about (not regarding/approximately), before (not prior
to). Delete "note that". Never write: delve, crucial, pivotal, robust,
seamless, foster, bolster, landscape (metaphor), tapestry, journey (metaphor),
navigate (metaphor), unpack, deep dive, at its core, in essence, holistic,
comprehensive, cutting-edge, game-changer, showcases, elevate, empower, unlock,
harness, spearhead, testament to, it's worth noting, in today's world, at the
end of the day. No filler intensifiers (genuinely, really, truly, actually,
simply, clearly, certainly, deeply, incredibly). Strip empty modals: "can help
improve" becomes "improves". Repeat the plain word instead of rotating synonyms.
Use verbs, not nominalizations ("we decided", not "the decision was made"). No
stacks of three or more nouns before a head noun.

Sentences: vary length hard. Put a four-word sentence next to a thirty-word one.
Prefer short independent clauses side by side. Do not write the balanced,
subordinated sentence that weighs two mirrored halves; it is the strongest
machine tell.

Do not produce: (1) corrective negation in any form ("not X but Y", "X, never
Y", "less about X than Y") — state the true thing once. (2) mirrored/antithetical
balance across clauses. (3) the rule of three; use two, or four, or one. (4)
cataphoric colon setups ("The result:", "Here's the thing:") — labeled data
fields the format asks for are fine. (5) definite-noun importance tags ("the fix
that matters"). (6) verdict-first apposition with a hedge tail ("Acceptable, with
one change"). (7) aphoristic quotable closers. (8) enumerated-noun headers ("Two
reasons") unless the count is information. (9) rhetorical questions you then
answer. (10) repeated sentence openers within a paragraph. (11) em dashes
anywhere; use a period, comma, colon (sparingly), or parentheses. (12) hedging
reflexes (arguably, generally speaking, tends to) — when unsure, say plainly what
you don't know. (13) closing recaps or "in short" takeaways. (14) participial
benefit tails (", making it easier to scale", ", ensuring consistency") — end the
sentence. (15) concessive openers staging balance ("While X, Y", "Although X,
Y"). (16) connective spam (Additionally, Furthermore, Moreover, Overall); however
at most once. (17) audience-flattering conditionals. (18) colon titles ("X: Why Y
Matters").

Open on substance, close on the last real point: no throat-clearing, no wrap-up,
no next-steps offer. In long output, re-apply these rules at every section.
Before returning, do one silent pass and rewrite any sentence that matches a
banned construction or shares its shape with a neighbor. Facts, numbers, links,
and quoted titles stay exactly as written."""


def _system(extra: str = "") -> str:
    """Shared system prompt for all prose-producing calls."""
    parts = [MISSION, PROSE_DIRECTIVE, LENS_DEF, SEC_LENS_DEF, LAW_LENS_DEF,
             SUBTOPIC_DEF, PE_SUBTOPIC_DEF, LAW_SUBTOPIC_DEF]
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "source": {"type": "string"},
                    "published": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "tags": {"type": "array", "items": {"type": "string", "enum": TAGS}},
                    "summary": {"type": "string"},
                    "privacy_angle": {"type": "string"},
                    "importance": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                    "pe_score": {"type": "integer", "enum": [0, 1, 2, 3]},
                    "pe_angle": {"type": "string"},
                    "sec_score": {"type": "integer", "enum": [0, 1, 2, 3]},
                    "sec_angle": {"type": "string"},
                    "law_score": {"type": "integer", "enum": [0, 1, 2, 3]},
                    "law_angle": {"type": "string"},
                    "subtopics": {"type": "array",
                                  "items": {"type": "string", "enum": SUBTOPICS}},
                    "pe_subtopics": {"type": "array",
                                     "items": {"type": "string", "enum": PE_SUBTOPICS}},
                    "law_subtopics": {"type": "array",
                                      "items": {"type": "string", "enum": LAW_SUBTOPICS}},
                },
                "required": ["title", "url", "source", "published", "tags",
                             "summary", "privacy_angle", "importance",
                             "pe_score", "pe_angle", "sec_score", "sec_angle",
                             "law_score", "law_angle", "subtopics",
                             "pe_subtopics", "law_subtopics"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}


def client_or_die() -> anthropic.Anthropic:
    c = anthropic.Anthropic()
    if not (c.api_key or c.auth_token or getattr(c, "credentials", None)):
        sys.exit(
            "No API credentials found.\n"
            "Set ANTHROPIC_API_KEY (e.g. `export ANTHROPIC_API_KEY=sk-ant-...`,\n"
            "or put it in a git-ignored .env file in the project root — \n"
            "scripts/daily-hunt-api.sh sources it automatically),\n"
            "or install the ant CLI and run `ant auth login`."
        )
    return c


def report_usage(usage, label: str) -> None:
    cost = (usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1e6
    cached = usage.cache_read_input_tokens or 0
    print(f"[{label}] {usage.input_tokens} in / {usage.output_tokens} out "
          f"({cached} cached) ~ ${cost:.3f}")


def guard_refusal(response) -> None:
    if response.stop_reason == "refusal":
        detail = ""
        if response.stop_details:
            detail = f" (category: {response.stop_details.category})"
        sys.exit(f"Claude declined this request{detail}. "
                 "This can happen with security content; re-run, or triage by hand.")


def triage(args) -> int:
    cand_file = ROOT / "data" / "feed-candidates.json"
    if not cand_file.exists():
        sys.exit("No data/feed-candidates.json — run scripts/fetch_feeds.py first.")
    data = json.loads(cand_file.read_text())
    candidates = data["candidates"]
    if not candidates:
        print("No candidates to triage.")
        return 0

    known = [{"title": i["title"], "url": i["url"]} for i in newsdb.load_items()]
    client = client_or_die()

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=BETAS,
        fallbacks="default",
        system=[{"type": "text", "text": _system(),
                 "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": ITEM_SCHEMA}},
        messages=[{
            "role": "user",
            "content": (
                "Triage these feed candidates into store-ready news items. "
                "For each kept item also fill the privacy, security, and law "
                "lenses (pe_score/pe_angle, sec_score/sec_angle, law_score/"
                "law_angle) and assign security subtopics, privacy subtopics "
                "(pe_subtopics), and legal subtopics (law_subtopics), all "
                "defined in the system prompt.\n\n"
                "Rules:\n"
                "- Keep only stories genuinely about privacy/security/compliance in "
                "agentic AI per the three lenses. Drop vendor fluff, generic AI news, "
                "and papers with only tangential privacy relevance.\n"
                "- Consolidate candidates covering the SAME story into one item, "
                "citing the best primary URL among those provided.\n"
                "- Use ONLY URLs that appear in the candidate list — never invent or "
                "modify a URL. For arXiv, prefer the /abs/ URL form if present.\n"
                "- Skip anything already covered in the known-items list below, "
                "unless a candidate is a material update to that story.\n"
                "- Summaries must be 2-3 factual sentences grounded strictly in the "
                "provided title and blurb — do not speculate beyond them.\n"
                "- privacy_angle: one sentence on why it matters for privacy in "
                "agentic AI.\n\n"
                f"Already in the store (skip these):\n{json.dumps(known, indent=1)}\n\n"
                f"Candidates:\n{json.dumps(candidates, indent=1)}"
            ),
        }],
    )
    guard_refusal(response)
    report_usage(response.usage, "triage")

    text = next(b.text for b in response.content if b.type == "text")
    items = json.loads(text)["items"]

    # safety net: drop any URL Claude didn't take verbatim from the candidates
    allowed = {c["url"].rstrip("/") for c in candidates}
    kept = [i for i in items if i["url"].rstrip("/") in allowed]
    if len(kept) < len(items):
        print(f"dropped {len(items) - len(kept)} item(s) with non-candidate URLs")

    out = ROOT / "data" / "triaged-items.json"
    out.write_text(json.dumps(kept, indent=2) + "\n")
    print(f"{len(kept)} items selected from {len(candidates)} candidates -> {out.relative_to(ROOT)}")
    if not args.no_ingest and kept:
        newsdb.ingest(str(out))
    return len(kept)


LENS_BACKFILL_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "pe_score": {"type": "integer", "enum": [0, 1, 2, 3]},
                    "pe_angle": {"type": "string"},
                    "sec_score": {"type": "integer", "enum": [0, 1, 2, 3]},
                    "sec_angle": {"type": "string"},
                    "law_score": {"type": "integer", "enum": [0, 1, 2, 3]},
                    "law_angle": {"type": "string"},
                    "subtopics": {"type": "array",
                                  "items": {"type": "string", "enum": SUBTOPICS}},
                    "pe_subtopics": {"type": "array",
                                     "items": {"type": "string", "enum": PE_SUBTOPICS}},
                    "law_subtopics": {"type": "array",
                                      "items": {"type": "string", "enum": LAW_SUBTOPICS}},
                },
                "required": ["id", "pe_score", "pe_angle", "sec_score",
                             "sec_angle", "law_score", "law_angle", "subtopics",
                             "pe_subtopics", "law_subtopics"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scores"],
    "additionalProperties": False,
}


def _needs_lens(i: dict) -> bool:
    return (i.get("pe_score") is None or i.get("sec_score") is None
            or i.get("law_score") is None or not i.get("subtopics")
            or "pe_subtopics" not in i or "law_subtopics" not in i)


def lens(args) -> None:
    """Backfill the privacy, security, and law lenses plus security subtopics."""
    items = newsdb.load_items()
    todo = items if args.all else [i for i in items if _needs_lens(i)]
    if not todo:
        print("All items already carry every lens. Use --all to re-score.")
        return
    client = client_or_die()
    scores = {}
    BATCH = 25  # keep each response well under the token cap so JSON stays intact
    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        payload = [{"id": i["id"], "title": i["title"], "tags": i["tags"],
                    "summary": i["summary"], "privacy_angle": i["privacy_angle"]}
                   for i in batch]
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=8000,
            betas=BETAS,
            fallbacks="default",
            system=[{"type": "text", "text": _system(),
                     "cache_control": {"type": "ephemeral"}}],
            output_config={"format": {"type": "json_schema", "schema": LENS_BACKFILL_SCHEMA}},
            messages=[{
                "role": "user",
                "content": (
                    "Score each story below on all three lenses (privacy, "
                    "security, law) and assign its security, privacy, and legal "
                    "subtopics, per the system prompt. Return one entry per "
                    "story, keyed by its id.\n\n"
                    f"{json.dumps(payload, indent=1)}"
                ),
            }],
        )
        guard_refusal(response)
        report_usage(response.usage, f"lens {start // BATCH + 1}")
        text = next(b.text for b in response.content if b.type == "text")
        for s in json.loads(text)["scores"]:
            scores[s["id"]] = s

    updated = 0
    for i in items:
        s = scores.get(i["id"])
        if s is None:
            continue
        for k in ("pe", "sec", "law"):
            i[f"{k}_score"] = max(0, min(3, int(s[f"{k}_score"])))
            i[f"{k}_angle"] = (s.get(f"{k}_angle") or "").strip()
        i["subtopics"] = [t for t in s.get("subtopics", []) if t in SUBTOPICS]
        i["pe_subtopics"] = [t for t in s.get("pe_subtopics", []) if t in PE_SUBTOPICS]
        i["law_subtopics"] = [t for t in s.get("law_subtopics", []) if t in LAW_SUBTOPICS]
        updated += 1
    (ROOT / "data" / "items.json").write_text(json.dumps(items, indent=2) + "\n")
    print(f"scored {updated} item(s) on privacy/security/law + subtopics")
    newsdb.build()


def _gen_digest(client, user_prompt: str, label: str, max_tokens: int = 6000) -> str:
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        betas=BETAS,
        fallbacks="default",
        system=[{"type": "text", "text": _system(),
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        response = stream.get_final_message()
    guard_refusal(response)
    report_usage(response.usage, label)
    return next(b.text for b in response.content if b.type == "text").strip() + "\n"


def digest(args) -> None:
    day = args.date or date.today().isoformat()
    cutoff = (date.fromisoformat(day) - timedelta(days=args.days - 1)).isoformat()
    items = [i for i in newsdb.load_items() if i["fetched"] >= cutoff]
    if not items:
        print(f"No items fetched since {cutoff}; nothing to digest.")
        return
    items.sort(key=lambda i: i["importance"], reverse=True)
    client = client_or_die()

    # 1) General digest — concise, plain-spoken, copy-paste friendly.
    general_prompt = (
        f"Write a CONCISE daily digest for {day} from the news items below "
        "(sorted by importance). Output ONLY the markdown document, no preamble:\n"
        f"- `# Daily Digest, {day}`\n"
        "- A bold **TL;DR:** paragraph, 3-4 short sentences, plain-spoken (avoid "
        "jargon and acronyms — say 'remote code execution', 'steals data', "
        "'breaks web protections' in everyday words), copy-paste friendly, with "
        "inline markdown links `[phrase](url)` on the 4-6 biggest stories woven "
        "into the sentences. Lead with the day's main theme, then the pattern "
        "tying stories together.\n"
        "- `## Top stories`: ONLY the 5-6 most important items. One bullet each: "
        "the bolded linked title, then `(Source, date)`, then a period, then one "
        "tight sentence (two at most) combining what happened and why it matters "
        "for privacy. No tag labels, no separate privacy-angle line.\n"
        "- `## Also notable`: up to 8 single-line bullets for the next items, each "
        "`[Title](url)` followed by a comma and a few words on what it is. Drop "
        "anything truly minor.\n"
        "Keep the whole thing tight. Use only URLs present in the items. Be "
        "factual; no speculation.\n\n"
        f"Items:\n{json.dumps(items, indent=1)}"
    )
    general = _gen_digest(client, general_prompt, "digest")
    (ROOT / "data" / "digests" / f"{day}.md").write_text(general)
    print(f"digest -> data/digests/{day}.md")

    # 2) Privacy-eng digest — same day, filtered/ranked by the pe lens.
    pe_items = sorted((i for i in items if (i.get("pe_score") or 0) >= 2),
                      key=lambda i: (i["pe_score"], i["importance"]), reverse=True)
    pe_path = ROOT / "data" / "digests" / f"{day}.pe.md"
    if pe_items:
        pe_view = [{"title": i["title"], "url": i["url"], "source": i["source"],
                    "published": i["published"], "pe_score": i["pe_score"],
                    "pe_angle": i["pe_angle"], "summary": i["summary"]}
                   for i in pe_items]
        pe_prompt = (
            f"Write a CONCISE privacy-engineering digest for {day}, for a privacy "
            "engineer building privacy capabilities into agentic systems. Output "
            "ONLY the markdown document, no preamble:\n"
            f"- `# Privacy-Eng Digest, {day}`\n"
            "- A bold **TL;DR:** 2-3 short sentences on what today's news means for "
            "that work (what to build or watch), with inline markdown "
            "links on the 2-4 most relevant stories.\n"
            "- `## What to watch`: the items below (already ranked by relevance). "
            "One bullet each: the bolded linked title, then `(Source)`, then a "
            "period, then one sentence leading "
            "with the concrete capability or control it informs (consent/permission "
            "UX, PII redaction, memory/identity isolation, differential privacy, "
            "data residency, agent auth, DLP/governance, etc.). Use the pe_angle as "
            "your guide; be specific about the control, not the attack.\n"
            "Keep it tight. Use only URLs present in the items. No fluff.\n\n"
            f"Items (ranked):\n{json.dumps(pe_view, indent=1)}"
        )
        pe_md = _gen_digest(client, pe_prompt, "digest:pe")
        pe_path.write_text(pe_md)
        print(f"privacy-eng digest -> data/digests/{day}.pe.md")
    elif pe_path.exists():
        pe_path.unlink()  # no pe-relevant items this run; drop a stale variant

    newsdb.build()


REPORTS = ROOT / "data" / "reports"


def report(args) -> None:
    """Delta report: only privacy-eng items not yet included in a prior report."""
    items = newsdb.load_items()
    new = [i for i in items if (i.get("pe_score") or 0) >= 2 and not i.get("reported")]
    REPORTS.mkdir(parents=True, exist_ok=True)
    state_file = REPORTS / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else \
        {"last_report_at": None, "count": 0}
    since = state.get("last_report_at")
    today = date.today().isoformat()

    if not new:
        note = (f"# Privacy Engineering Report, {today}\n\n"
                "No new privacy-engineering items since the last report"
                + (f" ({since[:10]})" if since else "") + ".\n")
        (REPORTS / "latest.md").write_text(note)
        print("No new privacy-eng items since the last report"
              + (f" ({since[:10]})." if since else "."))
        return

    new.sort(key=lambda i: (i["pe_score"], i["importance"]), reverse=True)
    view = [{"title": i["title"], "url": i["url"], "source": i["source"],
             "published": i["published"], "tags": i["tags"],
             "pe_score": i["pe_score"], "pe_angle": i["pe_angle"],
             "summary": i["summary"]} for i in new]
    client = client_or_die()
    prompt = (
        f"Write a CONCISE privacy-engineering intelligence report for {today}"
        + (f", covering ONLY what is new since the last report on {since[:10]}."
           if since else " (first baseline report).")
        + " Audience: a privacy engineering team tracking novel privacy and "
        "data-governance THREATS and SOLUTIONS across academia, research, and "
        "enterprise. Output ONLY markdown, no preamble:\n"
        f"- `# Privacy Engineering Report, {today}`"
        + (f" (new since {since[:10]})\n" if since else " (baseline)\n")
        + "- A bold **TL;DR:** 2-4 sentences on the most important new "
        "developments, both threats and solutions, with inline markdown links "
        "on the 3-5 biggest.\n"
        "- `## Novel threats & governance risks`: new attack classes, "
        "data-governance/privacy risks, notable exposures. One bullet each: the "
        "bolded linked title, then `(Source)`, then a period, then one sentence on "
        "the risk and what it means for privacy controls. Omit the section if "
        "there are none.\n"
        "- `## New capabilities & solutions`: defensive techniques/primitives "
        "(academia/research), standards, enterprise products/features, and "
        "regulation/governance. One bullet each: the bolded linked title, then "
        "`(Source)`, then a period, then one sentence leading with the "
        "capability/control it provides. Omit if none.\n"
        "Classify each item into exactly one section from its tags and pe_angle "
        "(a paper describing an ATTACK is a threat; defenses, products, regulation, "
        "and governance are solutions). Keep it tight and copy-paste friendly. Use "
        "only URLs present in the items.\n\n"
        f"Items (ranked by relevance):\n{json.dumps(view, indent=1)}"
    )
    # Steady-state deltas are small, but a first/baseline report clears the whole
    # backlog — give it room so it doesn't truncate.
    md = _gen_digest(client, prompt, "report", max_tokens=12000)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    (REPORTS / f"report-{stamp}.md").write_text(md)
    (REPORTS / "latest.md").write_text(md)

    ids = {i["id"] for i in new}
    for i in items:
        if i["id"] in ids:
            i["reported"] = True
    (ROOT / "data" / "items.json").write_text(json.dumps(items, indent=2) + "\n")
    state_file.write_text(json.dumps(
        {"last_report_at": datetime.now().isoformat(timespec="seconds"),
         "count": state.get("count", 0) + 1}, indent=1) + "\n")
    newsdb.build()
    print(f"report: {len(new)} new items -> data/reports/report-{stamp}.md")


def _arxiv_fulltext(url: str):
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+)", url)
    return f"https://arxiv.org/html/{m.group(1)}" if m else None


def synthesis(args) -> None:
    """Weekly deep synthesis: reads each paper's full text (web_fetch), then writes
    a mechanism-level, plain-language briefing framed by the privacy-by-design
    gap map. Windowed and STATELESS — does not touch the `reported` flag."""
    cutoff = (date.today() - timedelta(days=args.days - 1)).isoformat()
    pool = [i for i in newsdb.load_items()
            if (i.get("pe_score") or 0) >= 2 and i["fetched"] >= cutoff]
    if not pool:
        print(f"No privacy-eng items (pe_score>=2) in the last {args.days} days.")
        return
    pool.sort(key=lambda i: (i["pe_score"], i["importance"]), reverse=True)
    chosen = pool[:args.max]
    if len(pool) > len(chosen):
        print(f"synthesis covers the top {len(chosen)} of {len(pool)} pe items; "
              f"{len(pool) - len(chosen)} lower-ranked items dropped to bound "
              f"fetch cost (raise with --max).")

    view = []
    for i in chosen:
        e = {"title": i["title"], "url": i["url"], "source": i["source"],
             "published": i["published"], "tags": i["tags"],
             "pe_angle": i["pe_angle"], "summary": i["summary"]}
        ft = _arxiv_fulltext(i["url"])
        if ft:
            e["full_text_url"] = ft
        view.append(e)

    client = client_or_die()
    today = date.today().isoformat()
    system_text = _system(GUARDIAN_RUBRIC)
    tools = [{"type": "web_fetch_20260209", "name": "web_fetch",
              "max_uses": args.max * 2}]
    prompt = (
        f"Produce a WEEKLY privacy-engineering SYNTHESIS for {today}, covering the "
        f"window {cutoff} to {today}. Audience: a privacy engineering MANAGER "
        "leading a privacy-capabilities team. This is a "
        "mechanism-level briefing, not a high-level TL;DR.\n\n"
        "FIRST, use the web_fetch tool to read the actual content behind each item "
        "below. Prefer `full_text_url` when present (arXiv HTML full text); "
        "otherwise fetch `url`. Record for EACH item how deeply you could read it: "
        "'full text', 'abstract only', or 'blocked' (some sites return 403; say "
        "so rather than guessing). Base your analysis on what you actually read; "
        "never invent details you could not fetch.\n\n"
        "THEN write ONLY the markdown document, no preamble:\n"
        f"- `# Privacy Engineering Synthesis, {today}` (window {cutoff} to {today})\n"
        "- `## The big picture`: 2-4 short paragraphs on the LONGER-TERM industry "
        "trends this window reinforces, where things are heading, and the biggest "
        "unsolved problems.\n"
        "- `## Developments explained`: for the most important items, a "
        "`### [Title](url)` subsection with four labeled lines. **Read:** (full "
        "text / abstract only / blocked); **What it is (plain):** explain it for a "
        "smart reader new to this niche, plain vocabulary, no jargon; **How it "
        "works:** the actual mechanism, at technical depth; **So what for us:** the "
        "concrete implication for a privacy-capabilities team's roadmap.\n"
        "- `## Privacy-by-Design gap map`: for each Hoepman strategy and for "
        "data-subject rights (see the rubric in the system prompt), a bullet in the "
        "form `**STRATEGY** shipped this window: …; still missing: …`. This is the "
        "'where we need solutions' section. Be specific about the gaps.\n"
        "- `## Trends & where we need solutions`: a short prioritized list of the "
        "durable trends and the unsolved problems the team should invest in.\n"
        "- `## What The Guardian would veto`: patterns or technologies this "
        "window's evidence says a privacy team should refuse to adopt, and why.\n\n"
        "Write in plain language throughout but keep mechanism-level depth. Use "
        "only URLs present in the items.\n\n"
        f"Items to review (ranked):\n{json.dumps(view, indent=1)}"
    )
    messages = [{"role": "user", "content": prompt}]
    total_in = total_out = 0
    resp = None
    for _ in range(12):  # resume across pause_turn while web_fetch runs
        with client.messages.stream(
            model=MODEL, max_tokens=16000,
            system=[{"type": "text", "text": system_text,
                     "cache_control": {"type": "ephemeral"}}],
            tools=tools, messages=messages,
        ) as stream:
            resp = stream.get_final_message()
        total_in += resp.usage.input_tokens
        total_out += resp.usage.output_tokens
        guard_refusal(resp)
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    cost = (total_in * PRICE_IN + total_out * PRICE_OUT) / 1e6
    print(f"[synthesis] {total_in} in / {total_out} out ~ ${cost:.2f}")

    md = "".join(b.text for b in resp.content if b.type == "text").strip() + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    (REPORTS / f"synthesis-{stamp}.md").write_text(md)
    (REPORTS / "latest-synthesis.md").write_text(md)
    newsdb.build()  # surface the synthesis in the UI's persistent top panel
    print(f"synthesis -> data/reports/synthesis-{stamp}.md")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("triage", help="select + summarize feed candidates via Claude")
    t.add_argument("--no-ingest", action="store_true", help="write triaged-items.json only")
    d = sub.add_parser("digest", help="write the daily digest via Claude")
    d.add_argument("--date", help="digest date YYYY-MM-DD (default today)")
    d.add_argument("--days", type=int, default=1, help="include items fetched in the last N days")
    ln = sub.add_parser("lens", help="backfill privacy/security/law lenses + subtopics on stored items")
    ln.add_argument("--all", action="store_true", help="re-score every item, not just unscored ones")
    sub.add_parser("report", help="delta report: privacy-eng items new since the last report")
    sy = sub.add_parser("synthesis", help="weekly deep synthesis: reads each paper, /privacy-review framed")
    sy.add_argument("--days", type=int, default=14, help="window in days (default 14)")
    sy.add_argument("--max", type=int, default=15, help="max items to fetch+synthesize (default 15)")
    r = sub.add_parser("run", help="triage then digest")
    r.add_argument("--days", type=int, default=1)

    args = p.parse_args()
    if args.cmd == "triage":
        triage(args)
    elif args.cmd == "digest":
        digest(args)
    elif args.cmd == "lens":
        lens(args)
    elif args.cmd == "report":
        report(args)
    elif args.cmd == "synthesis":
        synthesis(args)
    else:
        args.no_ingest = False
        added = triage(args)
        args.date = None
        if added:
            digest(args)


if __name__ == "__main__":
    main()
