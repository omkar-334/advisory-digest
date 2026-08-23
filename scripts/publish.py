#!/usr/bin/env python3
"""Publish the latest validated run to the GitHub Pages site.

Reads the newest rows JSONL and contract summary from results/, and writes the three
files the dashboard fetches. Heal events are appended rather than replaced so the
timeline accumulates across runs.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / "results" / "validate"
DOCS = ROOT / "docs" / "data"


def newest(pattern: str):
    files = sorted(VALIDATE.glob(pattern))
    return files[-1] if files else None


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)

    summary_path = VALIDATE / "summary-latest.json"
    if not summary_path.exists():
        print("no contract summary yet; nothing to publish", file=sys.stderr)
        return 1
    summary = json.loads(summary_path.read_text())

    rows_path = newest("rows-*.jsonl")
    rows = []
    if rows_path:
        for line in rows_path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))

    # Drop anything resembling personal data before it reaches the published site.
    banned = {"author", "author_name", "byline", "email", "phone"}
    rows = [{k: v for k, v in r.items() if k.lower() not in banned} for r in rows]

    # A discovery-style collector can reach the same article by more than one path, so
    # the same story arrives several times. Deduplicate on the canonical article URL,
    # falling back to the title where a URL is missing.
    seen, deduped = set(), []
    for r in rows:
        key = (r.get("article_url") or "").strip().rstrip("/").lower() or \
              (r.get("title") or "").strip().lower()
        if key and key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    dropped = len(rows) - len(deduped)
    rows = deduped

    (DOCS / "latest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    (DOCS / "health.json").write_text(json.dumps(summary, indent=1))

    # Append a heal event when this run recorded one.
    heals_path = DOCS / "heals.json"
    heals = json.loads(heals_path.read_text()) if heals_path.exists() else []
    event_path = ROOT / "results" / "heal_loop" / "last-event.json"
    if event_path.exists():
        event = json.loads(event_path.read_text())
        if not any(h.get("stamp") == event.get("stamp") for h in heals):
            heals.append(event)
            heals_path.write_text(json.dumps(heals, indent=1))
        event_path.unlink()

    print(f"published {len(rows)} rows ({dropped} duplicates dropped), "
          f"{summary.get('healthy_sources')}/{summary.get('sources')} sources healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
