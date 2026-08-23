#!/usr/bin/env python3
"""Assign topics to collected articles with an LLM, replacing a hand-written regex list.

The first version of signals.py carried a dictionary of topics and the regexes that match
them. That is the same maintenance burden this project exists to argue against: every new
subject means editing a pattern, and every firm that phrases something differently is a
silent miss.

This classifies instead. It runs in two passes so labels stay consistent:

  1. propose a compact canonical taxonomy from a sample of the corpus
  2. assign each article one to three labels FROM that taxonomy, in batches

Batching matters: the model sees the canonical list every time, so it reuses labels rather
than inventing a synonym per batch. Output is docs/data/topics.json, keyed by article URL.

Stdlib only, via curl, so it runs wherever the rest of the pipeline runs.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from common import load_env, openai_json

load_env()

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "data"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
BATCH = 30
MAX_TOPICS = 22


def describe(row: dict) -> str:
    # Collectors sometimes emit nulls inside the tag list, so coerce rather than assume.
    tags = ", ".join(str(t) for t in (row.get("tags") or []) if t)
    title = str(row.get("title") or "").strip()
    summary = str(row.get("summary") or "")[:170]
    return " | ".join(x for x in (title, summary, tags) if x)


def build_taxonomy(rows: list[dict]) -> list[str]:
    sample = [describe(r) for r in rows[:110]]
    system = (
        "You are organising articles published by accounting, tax, audit and advisory firms.\n"
        "Propose a canonical topic taxonomy for this corpus.\n\n"
        "Rules:\n"
        f"- at most {MAX_TOPICS} topics\n"
        "- each topic is a subject a finance or accounting professional would recognise, "
        "such as a regulation, a service line or a risk area\n"
        "- prefer specific over generic: 'Section 174 / R&D capitalisation' beats 'Tax'\n"
        "- no overlapping or synonymous topics\n"
        "- topics must be reusable across firms, never named after one firm"
    )
    out = openai_json(system, "Articles:\n" + "\n".join(sample), '{"topics": [str]}')
    proposed = out.get("topics")
    if not isinstance(proposed, list):
        proposed = []
    topics = [t.strip() for t in proposed if isinstance(t, str) and t.strip()][:MAX_TOPICS]
    if not topics:
        raise RuntimeError("classifier returned no taxonomy")
    return topics


def assign(rows: list[dict], topics: list[str]) -> dict[str, list[str]]:
    system = (
        "Assign topics to each article from the CANONICAL LIST provided. Use only labels "
        "from that list, copied exactly.\n\n"
        "Rules:\n"
        "- one to three topics per article, most relevant first\n"
        "- if nothing in the list genuinely fits, return an empty list for that article. "
        "A wrong label is worse than no label, because these counts are used to claim that "
        "several firms independently covered the same subject."
    )
    valid = set(topics)
    canonical = "CANONICAL LIST:\n" + "\n".join(f"- {t}" for t in topics)
    mapping: dict[str, list[str]] = {}
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        listing = "\n".join(f"{i}. {describe(r)}" for i, r in enumerate(chunk))
        out = openai_json(system, f"{canonical}\n\nArticles:\n{listing}",
                   '{"assignments": [{"index": int, "topics": [str]}]}')
        assignments = out.get("assignments")
        for a in assignments if isinstance(assignments, list) else []:
            if not isinstance(a, dict):
                continue
            idx = a.get("index")
            # The model numbers the articles back to us, so the index is untrusted input:
            # an out-of-range one would silently label the wrong article.
            if not isinstance(idx, int) or not 0 <= idx < len(chunk):
                continue
            labels = [t for t in (a.get("topics") or []) if t in valid][:3]
            key = chunk[idx].get("article_url") or chunk[idx].get("title")
            if key and labels:
                mapping[key] = labels
        print(f"  classified {min(start + BATCH, len(rows))}/{len(rows)}")
    return mapping


def main() -> int:
    src = DOCS / "latest.json"
    if not src.exists():
        print("no published dataset", file=sys.stderr)
        return 1
    try:
        rows = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {src}: {exc}", file=sys.stderr)
        return 1
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    if not rows:
        print("published dataset is empty", file=sys.stderr)
        return 1

    # Every failure below is an API or reply problem. signals.py falls back to its regex
    # topics when topics.json is absent, so exiting without one degrades rather than breaks.
    try:
        print(f"building taxonomy from {len(rows)} articles using {MODEL}")
        topics = build_taxonomy(rows)
        print(f"  {len(topics)} topics: {', '.join(topics[:6])}...")
        mapping = assign(rows, topics)
    except RuntimeError as exc:
        print(f"classification failed: {exc}", file=sys.stderr)
        return 1

    (DOCS / "topics.json").write_text(
        json.dumps({"model": MODEL, "topics": topics, "assignments": mapping}, indent=1),
        encoding="utf-8")
    print(f"assigned topics to {len(mapping)}/{len(rows)} articles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
