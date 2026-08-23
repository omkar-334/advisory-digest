#!/usr/bin/env python3
"""Write a periodic digest: what moved since the last one, and what it means.

A dashboard is pull. Nobody opens one weekly. A digest is the same data pushed into a form
someone reads in thirty seconds: what is new, what several firms converged on, and what has
gone quiet.

Comparison is against the previous digest rather than an arbitrary window, so "new this
week" means new since you last read, not new since a fixed date. Runs on collected data
only -- no further scraping.

    digest.py [--period weekly|daily]

Writes docs/data/digest.json, keeping the last DIGEST_HISTORY editions.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from envfile import load_env

load_env()

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "data"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DIGEST_HISTORY = 8
PERIOD_DAYS = {"daily": 1, "weekly": 7}


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
        parsed = json.loads(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, ValueError) as exc:
        raise RuntimeError(f"Unexpected OpenAI response: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("model did not return an object")
    return parsed


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


DIGEST_SYSTEM = """You write a short briefing for finance and accounting professionals,
summarising what changed across a set of advisory firm newsrooms in one period.

Your reader is a controller or finance lead. They have thirty seconds. They want to know
whether anything happened that they should act on.

Rules:
- Ground everything in the supplied data. Never state a fact the data does not support.
- Lead with what several independent firms converged on, because that is the signal. A
  subject covered by one firm is not news.
- If nothing meaningful moved, say so plainly. A quiet week is a legitimate finding and is
  more useful than manufactured urgency.
- No greetings, no sign-off, no marketing language, no exclamation marks.
- headline: at most 12 words, specific, no colon-subtitle construction.
- summary: two or three sentences, at most 60 words total.
- watch: one sentence on what to keep an eye on, or an empty string if nothing warrants it."""

DIGEST_SCHEMA = '{"headline": str, "summary": str, "watch": str}'


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


def main(argv) -> int:
    period = "weekly"
    if "--period" in argv:
        idx = argv.index("--period")
        if idx + 1 < len(argv) and argv[idx + 1] in PERIOD_DAYS:
            period = argv[idx + 1]

    signals = read_json(DOCS / "signals.json")
    briefs = read_json(DOCS / "briefs.json", {})
    rows = read_json(DOCS / "latest.json", [])
    if not signals or not rows:
        print("no published data to summarise", file=sys.stderr)
        return 1

    existing = read_json(DOCS / "digest.json", {}) or {}
    editions = existing.get("editions", [])
    previous = editions[0] if editions else None
    seen_before = set(previous.get("subjects", [])) if previous else set()

    current = signals.get("signals") or []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=PERIOD_DAYS[period])

    # New means new since the last digest, not new since an arbitrary date: the reader's
    # question is "what changed since I last looked".
    new_subjects = [s for s in current if s["topic"] not in seen_before]
    widest = sorted(current, key=lambda s: s.get("firms", 0), reverse=True)[:5]
    quiet = sorted(seen_before - {s["topic"] for s in current})

    recent_articles = [r for r in rows
                       if (d := parse_date(r.get("published_date"))) and d >= cutoff]

    brief_by_topic = {b["topic"]: b for b in (briefs.get("briefs") or [])}
    lines = []
    for s in widest:
        b = brief_by_topic.get(s["topic"])
        detail = f" Consensus: {b['consensus']}" if b and b.get("consensus") else ""
        lines.append(f"- {s['topic']}: {s.get('firms')} firms, "
                     f"{s.get('articles')} articles.{detail}")

    user = (
        f"Period: last {PERIOD_DAYS[period]} day(s)\n"
        f"Articles published in period: {len(recent_articles)}\n"
        f"Subjects newly appearing since the previous digest: "
        f"{', '.join(s['topic'] for s in new_subjects) or 'none'}\n"
        f"Subjects that dropped out: {', '.join(quiet) or 'none'}\n\n"
        f"Widest cross-firm coverage:\n" + "\n".join(lines)
    )

    try:
        written = call(DIGEST_SYSTEM, user, DIGEST_SCHEMA)
    except RuntimeError as exc:
        print(f"could not write the digest: {exc}", file=sys.stderr)
        return 1

    edition = {
        "stamp": now.strftime("%Y%m%dT%H%M%SZ"),
        "date": now.date().isoformat(),
        "period": period,
        "headline": (written.get("headline") or "").strip(),
        "summary": (written.get("summary") or "").strip(),
        "watch": (written.get("watch") or "").strip(),
        "articles_in_period": len(recent_articles),
        "new_subjects": [s["topic"] for s in new_subjects][:6],
        "quiet_subjects": quiet[:6],
        "top": [{"topic": s["topic"], "firms": s.get("firms")} for s in widest],
        "subjects": [s["topic"] for s in current],
    }

    editions.insert(0, edition)
    (DOCS / "digest.json").write_text(json.dumps(
        {"model": MODEL, "editions": editions[:DIGEST_HISTORY]}, indent=1))

    print(f"{period} digest: {edition['headline']}")
    print(f"  {edition['summary']}")
    if edition["watch"]:
        print(f"  watch: {edition['watch']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
