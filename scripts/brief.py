#!/usr/bin/env python3
"""Turn each cross-firm signal into an answer instead of a list of links.

"Six firms wrote about Business Tax Compliance" plus twelve headlines is a reading list.
What someone actually wants to know is what those firms agree on, where they differ, and
whether it applies to them. That is a language problem over text already collected, so it
needs no further scraping.

Also computes lead-lag from the dates already stored: who published first on a subject and
how far ahead of the rest. That is arithmetic, not a model call, and it answers "who should
I be reading on this" without asking anyone.

Writes docs/data/briefs.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from envfile import load_env

load_env()

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "data"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_SUBJECTS = int(os.environ.get("BRIEF_MAX_SUBJECTS", "10"))


def call(system: str, user: str, schema: str) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system + "\n\nReturn JSON only: " + schema},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    proc = subprocess.run(
        ["curl", "-sS", "--max-time", "120",
         "https://api.openai.com/v1/chat/completions",
         "-H", f"Authorization: Bearer {key}",
         "-H", "Content-Type: application/json", "-d", "@-"],
        input=json.dumps(payload), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"OpenAI request failed: {proc.stderr.strip()[:200]}")
    try:
        body = json.loads(proc.stdout)
    except ValueError as exc:
        raise RuntimeError(f"OpenAI returned unreadable output: {exc}") from exc
    if "error" in body:
        raise RuntimeError(f"OpenAI error: {body['error'].get('message', '')[:200]}")
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected OpenAI response shape: {exc}") from exc
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("classifier did not return an object")
    return parsed


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


SYNTHETIC_FIRMS = {"advisory-digest.vercel.app"}


def firm_of(row) -> str:
    return (row.get("_firm") or "unknown").strip() or "unknown"


def is_real_firm(firm) -> bool:
    """The control page is our own fixture, not a source of coverage."""
    return bool(firm) and firm not in SYNTHETIC_FIRMS


# A lead is only a lead if the others were reacting to the same thing. Firms write about
# SALT every year, so "first by 439 days" is not a scoop, it is unrelated older coverage.
# Only a burst -- several firms publishing close together -- supports the claim.
BURST_WINDOW_DAYS = int(os.environ.get("BRIEF_BURST_DAYS", "45"))
MIN_BURST_FIRMS = 3


def lead_lag(articles):
    """Who published first within a burst of coverage, and how far ahead.

    Returns None unless at least MIN_BURST_FIRMS distinct firms published within
    BURST_WINDOW_DAYS of each other. Without that constraint the "lead" is just an artefact
    of how far back the archive happens to reach.
    """
    dated = sorted(
        ((d, a) for d, a in ((parse_date(x.get("published_date")), x) for x in articles) if d),
        key=lambda pair: pair[0],
    )
    if len(dated) < 2:
        return None

    # Widest burst: for each start, take everything inside the window and count firms.
    best = None
    for i, (start, _) in enumerate(dated):
        window = [(d, a) for d, a in dated[i:]
                  if (d - start).days <= BURST_WINDOW_DAYS]
        firms = {firm_of(a) for _, a in window}
        if len(firms) < MIN_BURST_FIRMS:
            continue
        # Prefer the most recent qualifying burst, then the broadest.
        score = (start, len(firms))
        if best is None or score > best[0]:
            best = (score, window)

    if best is None:
        return None

    window = best[1]
    first_date, first_article = window[0]
    first_firm = firm_of(first_article)
    follower = next((d for d, a in window if firm_of(a) != first_firm), None)
    if follower is None:
        return None

    return {
        "first_firm": first_firm,
        "first_date": first_date.date().isoformat(),
        "first_title": first_article.get("title"),
        "first_url": first_article.get("article_url"),
        "lead_days": (follower - first_date).days,
        "burst_firms": len({firm_of(a) for _, a in window}),
        "burst_days": BURST_WINDOW_DAYS,
        "followers": sorted({firm_of(a) for _, a in window if firm_of(a) != first_firm}),
    }


BRIEF_SYSTEM = """You write short briefings for finance and accounting professionals, from
articles published by advisory firms on one subject.

Your reader is a controller or finance lead at a mid-market company. They do not want a
summary of each article. They want to know what the profession is saying, where it disagrees,
and whether it applies to them.

Rules:
- Ground every statement in the supplied articles. Do not add outside knowledge, and do not
  state anything the articles do not support.
- Where firms differ in emphasis or interpretation, say so and name them. If they do not
  visibly differ, say that plainly rather than inventing a disagreement.
- "applies_to" describes the kind of business affected, in plain terms. If the articles do
  not say, return an empty string rather than guessing.
- No marketing language, no hedging filler, no restating the subject name.
- consensus: at most 45 words. divergence: at most 35 words. applies_to: at most 25 words."""

BRIEF_SCHEMA = ('{"consensus": str, "divergence": str, "applies_to": str, '
                '"confidence": "high"|"medium"|"low"}')


def brief_for(topic, articles):
    listing = "\n".join(
        f"- [{firm_of(a)}] {a.get('title', '')}: {(a.get('summary') or '')[:260]}"
        for a in articles[:14]
    )
    user = (f"Subject: {topic}\n"
            f"Firms covering it: {len({firm_of(a) for a in articles})}\n\n"
            f"Articles:\n{listing}")
    return call(BRIEF_SYSTEM, user, BRIEF_SCHEMA)


def refresh_lead(rows, assignments) -> int:
    """Recompute lead-lag on existing briefs. The written text is expensive; this is not."""
    path = DOCS / "briefs.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"no briefs to refresh: {exc}", file=sys.stderr)
        return 1

    by_key = {(r.get("article_url") or r.get("title")): r
              for r in rows if is_real_firm(firm_of(r))}
    for brief in payload.get("briefs", []):
        articles = [by_key[k] for k, labels in assignments.items()
                    if brief["topic"] in labels and k in by_key]
        brief["lead"] = lead_lag(articles)
    path.write_text(json.dumps(payload, indent=1))
    kept = sum(1 for b in payload.get("briefs", []) if b.get("lead"))
    print(f"refreshed lead-lag on {len(payload.get('briefs', []))} briefs; "
          f"{kept} have a defensible burst")
    return 0


def main() -> int:
    try:
        rows = json.loads((DOCS / "latest.json").read_text(encoding="utf-8"))
        signals = json.loads((DOCS / "signals.json").read_text(encoding="utf-8"))
        topics = json.loads((DOCS / "topics.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read published data: {exc}", file=sys.stderr)
        return 1

    assignments = topics.get("assignments") or {}
    if "--refresh-lead" in sys.argv:
        return refresh_lead(rows, assignments)

    rows = [r for r in rows if is_real_firm(firm_of(r))]
    by_key = {(r.get("article_url") or r.get("title")): r for r in rows}

    briefs = []
    for sig in (signals.get("signals") or [])[:MAX_SUBJECTS]:
        topic = sig.get("topic")
        articles = [by_key[k] for k, labels in assignments.items()
                    if topic in labels and k in by_key]
        if len(articles) < 2:
            continue

        print(f"  briefing: {topic} ({len(articles)} articles)")
        try:
            written = brief_for(topic, articles)
        except RuntimeError as exc:
            print(f"    skipped: {exc}", file=sys.stderr)
            continue

        briefs.append({
            "topic": topic,
            "firms": sig.get("firms"),
            "firm_list": sig.get("firm_list", []),
            "articles": len(articles),
            "consensus": (written.get("consensus") or "").strip(),
            "divergence": (written.get("divergence") or "").strip(),
            "applies_to": (written.get("applies_to") or "").strip(),
            "confidence": written.get("confidence", "medium"),
            "lead": lead_lag(articles),
        })

    (DOCS / "briefs.json").write_text(json.dumps(
        {"model": MODEL, "generated_from": len(rows), "briefs": briefs}, indent=1))
    print(f"wrote {len(briefs)} briefs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
