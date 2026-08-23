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

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "data"
RECENT_DAYS = 30
MIN_FIRMS = 2

# Subjects worth tracking, with the surface forms firms actually use for them. Kept
# explicit rather than inferred: a wrong cluster is worse than a missing one here.
TOPICS = {
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


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    for fn in (datetime.fromisoformat, lambda t: datetime.strptime(t[:10], "%Y-%m-%d")):
        try:
            dt = fn(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def main() -> int:
    src = DOCS / "latest.json"
    if not src.exists():
        print("no published dataset yet", file=sys.stderr)
        return 1
    rows = json.loads(src.read_text())
    if not rows:
        print("published dataset is empty", file=sys.stderr)
        return 1

    dates = [d for d in (parse_date(r.get("published_date")) for r in rows) if d]
    now = max(dates) if dates else datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENT_DAYS)

    signals = []
    for topic, pattern in TOPICS.items():
        rx = re.compile(pattern, re.I)
        by_firm = defaultdict(list)
        for r in rows:
            haystack = " ".join([
                r.get("title") or "", r.get("summary") or "",
                " ".join(r.get("tags") or []),
            ])
            if rx.search(haystack):
                by_firm[r.get("_firm", "unknown")].append(r)

        if len(by_firm) < MIN_FIRMS:
            continue

        articles = [a for arts in by_firm.values() for a in arts]
        recent = [a for a in articles
                  if (d := parse_date(a.get("published_date"))) and d >= cutoff]
        recent_firms = sorted({a.get("_firm") for a in recent}) or sorted(by_firm)

        signals.append({
            "topic": topic,
            "firms": len(by_firm),
            "firm_list": sorted(by_firm),
            "articles": len(articles),
            "recent_articles": len(recent),
            "recent_firms": len(recent_firms),
            "examples": [
                {"title": a.get("title"), "firm": a.get("_firm"),
                 "url": a.get("article_url"), "date": a.get("published_date")}
                for a in sorted(recent or articles,
                                key=lambda x: parse_date(x.get("published_date")) or cutoff,
                                reverse=True)[:4]
            ],
        })

    # Rank by breadth of independent coverage first, then by how much of it is recent.
    signals.sort(key=lambda s: (s["recent_firms"], s["firms"], s["recent_articles"]),
                 reverse=True)

    out = {
        "generated_from": len(rows),
        "window_days": RECENT_DAYS,
        "as_of": now.date().isoformat(),
        "signals": signals,
    }
    (DOCS / "signals.json").write_text(json.dumps(out, indent=1))
    print(f"{len(signals)} cross-firm signals from {len(rows)} articles")
    for s in signals[:6]:
        print(f"  {s['recent_firms']:2d} firms | {s['topic']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
