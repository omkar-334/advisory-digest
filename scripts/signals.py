#!/usr/bin/env python3
"""Derive cross-firm signals from the collected articles.

A single firm's newsroom tells you what that firm thinks. The point of collecting a dozen
of them is that agreement between independent firms carries information no single site
does: when several firms publish on the same subject in the same week, something changed.

This computes, per topic:
  firms   how many DISTINCT firms covered it (the signal; one firm publishing five times
          is marketing, five firms publishing once each is a development)
  recent  how many of those articles fall inside the recent window
  surge   recent share relative to the topic's overall rate

Output feeds the Signals view on the dashboard.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import firm_of, is_real_firm, parse_date

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "data"
RECENT_DAYS = 30
MIN_FIRMS = 2

# Fallback only. scripts/classify_topics.py produces docs/data/topics.json with LLM-assigned
# labels, which is what this uses when present. These patterns exist so the pipeline still
# produces signals with no API key and no network, e.g. in CI on a fork.
FALLBACK_TOPICS = {
    "Section 174 / R&D capitalisation": r"section\s*174|r&d\s*(capitali|expens|credit)|research\s+and\s+experimental",
    "Tariffs and trade": r"\btariff|trade\s+polic|customs\s+dut|import\s+dut",
    "Revenue recognition (ASC 606)": r"asc\s*606|revenue\s+recognition",
    "Lease accounting (ASC 842)": r"asc\s*842|lease\s+account",
    "AI adoption and governance": r"\bAI\b|artificial\s+intelligence|machine\s+learning|generative",
    "Cybersecurity and data privacy": r"cyber|ransomware|data\s+privacy|breach|infosec",
    "State and local tax (SALT)": r"\bSALT\b|state\s+and\s+local\s+tax|pass-through\s+entity|nexus",
    "Transfer pricing": r"transfer\s+pricing|intercompany\s+pric",
    "ESG and sustainability reporting": r"\bESG\b|sustainab|climate\s+disclos|emissions",
    "Mergers and acquisitions": r"\bM&A\b|merger|acquisition|due\s+diligence",
    "Private equity": r"private\s+equity|\bPE\s+firm|portfolio\s+company",
    "Workforce and talent": r"workforce|talent|hiring|human\s+capital|retention",
    "Audit quality and readiness": r"audit\s+(readiness|quality|committee)|internal\s+control|SOX",
    "Digital transformation / ERP": r"\bERP\b|digital\s+transformation|cloud\s+migration|automation",
    "Healthcare regulation": r"healthcare|medicaid|medicare|provider\s+reimburse",
    "Financial services regulation": r"bank(ing)?\s+regulat|basel|capital\s+requirement|credit\s+union",
    "Construction and real estate": r"construction|real\s+estate|\bREIT\b",
    "Nonprofit and government contracting": r"nonprofit|not-for-profit|government\s+contract|\bGovCon\b",
}




def haystack(row: dict) -> str:
    # Collectors sometimes emit nulls inside the tag list, so coerce rather than assume.
    tags = " ".join(str(t) for t in (row.get("tags") or []) if t)
    return " ".join([row.get("title") or "", row.get("summary") or "", tags])


def main() -> int:
    src = DOCS / "latest.json"
    if not src.exists():
        print("no published dataset yet", file=sys.stderr)
        return 1
    try:
        rows = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {src}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(rows, list):
        print(f"{src} is not a list of articles", file=sys.stderr)
        return 1
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        print("published dataset is empty", file=sys.stderr)
        return 1

    # Some firms publish future-dated items (registration pages for upcoming webinars), so
    # taking the maximum date would report the corpus as being "as of" months from now.
    today = datetime.now(timezone.utc)
    dates = [d for d in (parse_date(r.get("published_date")) for r in rows)
             if d and d <= today]
    now = max(dates) if dates else today
    cutoff = now - timedelta(days=RECENT_DAYS)

    rows = [r for r in rows if is_real_firm((r.get("_firm") or "").strip())]
    if not rows:
        print("no rows from real sources", file=sys.stderr)
        return 1

    # Prefer LLM-assigned topics; fall back to patterns when they are not available.
    topics_path = DOCS / "topics.json"
    assigned, source = {}, "regex-fallback"
    if topics_path.exists():
        try:
            payload = json.loads(topics_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        candidate = payload.get("assignments") if isinstance(payload, dict) else None
        if isinstance(candidate, dict) and candidate:
            assigned = candidate
            source = f"llm:{payload.get('model') or 'unknown'}"

    if assigned:
        grouped = defaultdict(lambda: defaultdict(list))
        for r in rows:
            key = r.get("article_url") or r.get("title")
            for topic in assigned.get(key) or []:
                grouped[topic][firm_of(r)].append(r)
        by_topic = list(grouped.items())
    else:
        by_topic = []
        for topic, pattern in FALLBACK_TOPICS.items():
            rx = re.compile(pattern, re.I)
            by_firm = defaultdict(list)
            for r in rows:
                if rx.search(haystack(r)):
                    by_firm[firm_of(r)].append(r)
            if by_firm:
                by_topic.append((topic, by_firm))

    signals = []
    for topic, by_firm in by_topic:
        if len(by_firm) < MIN_FIRMS:
            continue

        articles = [a for arts in by_firm.values() for a in arts]
        recent = [a for a in articles
                  if (d := parse_date(a.get("published_date"))) and d >= cutoff]
        recent_firms = sorted({firm_of(a) for a in recent}) or sorted(by_firm)

        signals.append({
            "topic": topic,
            "firms": len(by_firm),
            "firm_list": sorted(by_firm),
            "articles": len(articles),
            "recent_articles": len(recent),
            "recent_firms": len(recent_firms),
            "examples": [
                {"title": a.get("title"), "firm": firm_of(a),
                 "url": a.get("article_url"), "date": a.get("published_date")}
                for a in sorted(recent or articles,
                                key=lambda x: parse_date(x.get("published_date")) or cutoff,
                                reverse=True)[:4]
            ],
        })

    # Rank by breadth of independent coverage first, then by how much of it is recent.
    signals.sort(key=lambda s: (s["recent_firms"], s["firms"], s["recent_articles"]),
                 reverse=True)

    # Which subjects are covered by the same firms. Two subjects sharing most of their
    # coverage are being pushed by the same houses, which is a different fact from two
    # subjects merely both being popular. Computed here rather than drawn as a node graph:
    # the number of shared firms is the information, and a hairball hides it.
    cooccurrence = []
    for i, a in enumerate(signals):
        firms_a = set(a["firm_list"])
        for b in signals[i + 1:]:
            shared = firms_a & set(b["firm_list"])
            if len(shared) >= 2:
                cooccurrence.append({
                    "a": a["topic"],
                    "b": b["topic"],
                    "shared": len(shared),
                    "firms": sorted(shared),
                })
    cooccurrence.sort(key=lambda c: c["shared"], reverse=True)

    out = {
        "topic_source": source,
        "cooccurrence": cooccurrence[:40],
        "generated_from": len(rows),
        "window_days": RECENT_DAYS,
        "as_of": now.date().isoformat(),
        "signals": signals,
    }
    (DOCS / "signals.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{len(signals)} cross-firm signals from {len(rows)} articles")
    for s in signals[:6]:
        print(f"  {s['recent_firms']:2d} firms | {s['topic']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
