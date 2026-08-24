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
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import firm_of, load_env, openai_json, parse_date, read_json

load_env()

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "data"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DIGEST_HISTORY = 8
# A week with almost nothing in it produces an edition that says nothing.
MIN_ARTICLES_PER_EDITION = 4
# Each edition looks back this far. A week alone is too thin for cross-firm agreement.
WINDOW_DAYS = 28
PERIOD_DAYS = {"daily": 1, "weekly": 7}


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


def week_of(dt):
    """ISO year and week, which is how a reader thinks about "last week"."""
    y, w, _ = dt.isocalendar()
    return (y, w)


def subjects_in(articles, assignments):
    """Which subjects these articles covered, and how many distinct firms covered each."""
    by_topic: dict[str, set] = {}
    for a in articles:
        key = a.get("article_url") or a.get("title")
        for topic in assignments.get(key, []):
            by_topic.setdefault(topic, set()).add(firm_of(a))
    return {t: firms for t, firms in by_topic.items() if len(firms) >= 2}


def write_edition(articles, previous_subjects, label, when, brief_by_topic):
    """Ask for one edition. Returns the record, or None if the model could not write it."""
    subjects = subjects_in(articles, write_edition.assignments)
    ranked = sorted(subjects.items(), key=lambda kv: len(kv[1]), reverse=True)[:5]

    lines = []
    for topic, firms in ranked:
        b = brief_by_topic.get(topic)
        detail = f" Consensus: {b['consensus']}" if b and b.get("consensus") else ""
        lines.append(f"- {topic}: {len(firms)} firms.{detail}")

    new_subjects = [t for t, _ in ranked if t not in previous_subjects]
    user = (f"Period: {label}\n"
            f"Articles published in period: {len(articles)}\n"
            f"Subjects newly appearing since the previous period: "
            f"{', '.join(new_subjects) or 'none'}\n\n"
            f"Widest cross-firm coverage:\n" + ("\n".join(lines) or "- nothing covered by "
            "more than one firm"))

    try:
        written = openai_json(DIGEST_SYSTEM, user, DIGEST_SCHEMA)
    except RuntimeError as exc:
        print(f"  {label}: could not write ({exc})", file=sys.stderr)
        return None

    return {
        "stamp": when.strftime("%Y%m%dT%H%M%SZ"),
        "date": when.date().isoformat(),
        "period": "rolling",
        "window_days": WINDOW_DAYS,
        "label": label,
        "headline": (written.get("headline") or "").strip(),
        "summary": (written.get("summary") or "").strip(),
        "watch": (written.get("watch") or "").strip(),
        "articles_in_period": len(articles),
        "new_subjects": new_subjects[:6],
        "top": [{"topic": t, "firms": len(f)} for t, f in ranked],
        "subjects": [t for t, _ in ranked],
    }


def backfill(weeks: int) -> int:
    """Write one edition per ISO week from the dates already collected.

    Not synthetic: each edition describes what was actually published in that week. It
    exists because a single edition cannot show a trend, and the dates to build the history
    from are already in the dataset.
    """
    rows = read_json(DOCS / "latest.json", [])
    briefs = read_json(DOCS / "briefs.json", {}) or {}
    topics = read_json(DOCS / "topics.json", {}) or {}
    if not rows:
        print("no published dataset", file=sys.stderr)
        return 1

    write_edition.assignments = topics.get("assignments") or {}
    brief_by_topic = {b["topic"]: b for b in (briefs.get("briefs") or [])}

    now = datetime.now(timezone.utc)
    dated = [(d, r) for d, r in ((parse_date(r.get("published_date")), r) for r in rows)
             if d and d <= now]
    if not dated:
        print("no usable dates", file=sys.stderr)
        return 1

    by_week: dict[tuple, list] = {}
    for d, r in dated:
        by_week.setdefault(week_of(d), []).append(r)

    # Each edition covers a rolling window ending that week, not the week alone. At eight to
    # ten articles a week across eleven firms, two firms rarely land on the same subject
    # inside seven days, so a strictly weekly edition reports "nothing happened" almost
    # every time -- true, but useless. The window is where the cross-firm signal lives.
    recent = [wk for wk in sorted(by_week, reverse=True)
              if len(by_week[wk]) >= MIN_ARTICLES_PER_EDITION][:weeks]
    if not recent:
        print("no week has enough articles for an edition", file=sys.stderr)
        return 1

    editions = []
    seen_subjects: set[str] = set()
    # Build oldest first so "new since last time" means what it says.
    for wk in reversed(recent):
        when = max(d for d, r in dated if week_of(d) == wk)
        window_start = when - timedelta(days=WINDOW_DAYS)
        articles = [r for d, r in dated if window_start < d <= when]
        label = when.strftime("%-d %b %Y")
        edition = write_edition(articles, seen_subjects, label, when, brief_by_topic)
        if edition:
            editions.append(edition)
            seen_subjects.update(edition["subjects"])
            print(f"  {label}: {edition['headline']}")

    editions.reverse()
    (DOCS / "digest.json").write_text(json.dumps(
        {"model": MODEL, "editions": editions}, indent=1), encoding="utf-8")
    print(f"wrote {len(editions)} weekly editions")
    return 0


def main(argv) -> int:
    if "--backfill" in argv:
        idx = argv.index("--backfill")
        weeks = int(argv[idx + 1]) if idx + 1 < len(argv) and argv[idx + 1].isdigit() else 6
        return backfill(weeks)


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
        written = openai_json(DIGEST_SYSTEM, user, DIGEST_SCHEMA)
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
