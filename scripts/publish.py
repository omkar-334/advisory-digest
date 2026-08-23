#!/usr/bin/env python3
"""Publish the latest validated run to the GitHub Pages site.

Reads the newest rows JSONL and contract summary from results/, and writes the three
files the dashboard fetches. Heal events are appended rather than replaced so the
timeline accumulates across runs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / "results" / "validate"
DOCS = ROOT / "docs" / "data"

# Kept in step with validate.py's FORBIDDEN_FIELDS. The contract rejects a run that
# collects these; this is the second line of defence, in case a row reaches the site
# through an older summary.
FORBIDDEN_FIELDS = {"author", "author_name", "byline", "email", "phone"}


def newest(pattern: str) -> Path | None:
    files = sorted(VALIDATE.glob(pattern))
    return files[-1] if files else None


def read_json(path: Path, default):
    """Read JSON, falling back to `default` and saying so. Every file read here is a
    build artefact that a killed run can leave half-written."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"could not read {path}: {exc}", file=sys.stderr)
        return default


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)

    summary_path = VALIDATE / "summary-latest.json"
    if not summary_path.exists():
        print("no contract summary yet; nothing to publish", file=sys.stderr)
        return 1
    summary = read_json(summary_path, None)
    if not isinstance(summary, dict):
        print(f"{summary_path} is not a contract summary", file=sys.stderr)
        return 1

    rows_path = newest("rows-*.jsonl")
    rows = []
    if rows_path:
        for number, line in enumerate(rows_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                # A run killed mid-write leaves a truncated last line. One unreadable row
                # is not a reason to withhold the rest of the dataset.
                print(f"skipping unreadable row {rows_path.name}:{number}", file=sys.stderr)
                continue
            if isinstance(row, dict):
                rows.append(row)

    rows = [{k: v for k, v in r.items() if k.lower() not in FORBIDDEN_FIELDS} for r in rows]

    # A discovery-style collector can reach the same article by more than one path, so
    # the same story arrives several times. Deduplicate on the canonical article URL,
    # falling back to the title where a URL is missing.
    seen: set[str] = set()
    deduped = []
    for r in rows:
        key = ((r.get("article_url") or "").strip().rstrip("/").lower()
               or (r.get("title") or "").strip().lower())
        if key in seen:
            continue
        # A row with neither a URL nor a title has no identity to deduplicate on, so it
        # is kept rather than collapsing every such row into one.
        if key:
            seen.add(key)
        deduped.append(r)
    dropped = len(rows) - len(deduped)
    rows = deduped

    # Never overwrite a good dataset with an empty one. This exact failure happened in CI:
    # the row JSONL is gitignored, so a fresh checkout whose scrape had failed still found
    # the committed summary, published zero rows, and blanked the live site.
    if not rows:
        existing = read_json(DOCS / "latest.json", [])
        had = len(existing) if isinstance(existing, list) else 0
        print(f"refusing to publish 0 rows over {had} existing rows", file=sys.stderr)
        return 1

    (DOCS / "latest.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (DOCS / "health.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    heals_path = DOCS / "heals.json"
    event_path = ROOT / "results" / "heal_loop" / "last-event.json"
    if event_path.exists():
        heals = read_json(heals_path, None) if heals_path.exists() else []
        event = read_json(event_path, None)
        if not isinstance(heals, list) or not isinstance(event, dict):
            # Leave both files untouched: rewriting an unreadable timeline would discard
            # every earlier repair, and the event is still there for the next publish.
            print("skipping the heal timeline this run", file=sys.stderr)
        else:
            # The control page is ours, broken on purpose to prove the loop runs unattended.
            # It is recorded as a verification rather than mixed in with real source repairs.
            event.setdefault(
                "kind",
                "verification" if "advisory-digest" in (event.get("firm") or "") else "production",
            )
            if not any(h.get("stamp") == event.get("stamp")
                       for h in heals if isinstance(h, dict)):
                heals.append(event)
                heals_path.write_text(json.dumps(heals, indent=1), encoding="utf-8")
            event_path.unlink()

    print(f"published {len(rows)} rows ({dropped} duplicates dropped), "
          f"{summary.get('healthy_sources')}/{summary.get('sources')} sources healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
