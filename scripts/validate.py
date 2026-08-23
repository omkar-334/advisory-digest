#!/usr/bin/env python3
"""Output contract for the Zed releases scraper.

This file is the single definition of "healthy scraper output". CI runs it after
every scrape. When it fails, its diagnosis becomes the prompt handed to
`bdata scraper heal`, which is what makes the heal loop autonomous.

Exit codes:
  0  contract satisfied
  2  contract violated (heal-worthy: the scraper ran but the data is wrong)
  1  hard error (bad input file, unreadable JSON: not something heal can fix)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MIN_ROWS = int(os.environ.get("CONTRACT_MIN_ROWS", "5"))
MIN_FIELD_COVERAGE = float(os.environ.get("CONTRACT_MIN_COVERAGE", "0.8"))

REQUIRED_FIELDS = ("version", "channel", "release_date", "release_url")
VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?")
URL_RE = re.compile(r"^https?://", re.I)
VALID_CHANNELS = {"stable", "preview"}


def _rows(payload):
    """Unwrap the several shapes a collector run can return."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "rows", "items", "output"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        if any(f in payload for f in REQUIRED_FIELDS):
            return [payload]
    return []


def _iso_ok(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip().replace("Z", "+00:00")
    for parse in (
        lambda t: datetime.fromisoformat(t),
        lambda t: datetime.strptime(t[:10], "%Y-%m-%d"),
    ):
        try:
            parse(text)
            return True
        except ValueError:
            continue
    return False


def check(rows):
    """Return (violations, coverage) where violations are human-readable strings."""
    violations = []
    if not rows:
        return ["The scraper returned zero rows. No releases were extracted at all."], {}

    if len(rows) < MIN_ROWS:
        violations.append(
            f"Only {len(rows)} release(s) were extracted but the page always lists at "
            f"least {MIN_ROWS}. The scraper is likely matching only the first block "
            f"instead of iterating over every release on the page."
        )

    coverage = {}
    for field in REQUIRED_FIELDS:
        present = sum(1 for r in rows if isinstance(r, dict) and r.get(field) not in (None, "", []))
        coverage[field] = present / len(rows)
        if coverage[field] < MIN_FIELD_COVERAGE:
            violations.append(
                f"The '{field}' field is missing or empty on "
                f"{len(rows) - present} of {len(rows)} rows "
                f"({coverage[field]:.0%} populated). Its selector no longer matches the page."
            )

    bad_version = [r.get("version") for r in rows
                   if isinstance(r, dict) and r.get("version")
                   and not VERSION_RE.match(str(r["version"]).strip())]
    if bad_version:
        violations.append(
            f"{len(bad_version)} row(s) have a 'version' that is not a version number, "
            f"e.g. {bad_version[0]!r}. The selector is picking up the wrong element."
        )

    bad_channel = [r.get("channel") for r in rows
                   if isinstance(r, dict) and r.get("channel")
                   and str(r["channel"]).strip().lower() not in VALID_CHANNELS]
    if bad_channel:
        violations.append(
            f"{len(bad_channel)} row(s) have a 'channel' outside {sorted(VALID_CHANNELS)}, "
            f"e.g. {bad_channel[0]!r}."
        )

    bad_url = [r.get("release_url") for r in rows
               if isinstance(r, dict) and r.get("release_url")
               and not URL_RE.match(str(r["release_url"]).strip())]
    if bad_url:
        violations.append(
            f"{len(bad_url)} row(s) have a 'release_url' that is not an absolute URL, "
            f"e.g. {bad_url[0]!r}. Relative hrefs must be resolved against https://zed.dev."
        )

    bad_date = [r.get("release_date") for r in rows
                if isinstance(r, dict) and r.get("release_date")
                and not _iso_ok(r["release_date"])]
    if bad_date:
        violations.append(
            f"{len(bad_date)} row(s) have a 'release_date' that is not an ISO 8601 date, "
            f"e.g. {bad_date[0]!r}."
        )

    empty_notes = sum(1 for r in rows if isinstance(r, dict)
                      and not (r.get("changelog_items") or []))
    if empty_notes / len(rows) > (1 - MIN_FIELD_COVERAGE):
        violations.append(
            f"'changelog_items' is empty on {empty_notes} of {len(rows)} rows. The "
            f"bullet list under each release is no longer being collected."
        )

    return violations, coverage


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate.py <run-output.json> [results-dir]", file=sys.stderr)
        return 1

    src = Path(sys.argv[1])
    outdir = Path(sys.argv[2] if len(sys.argv) > 2 else "results/validate")
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = time.time()

    try:
        payload = json.loads(src.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"HARD ERROR: cannot read {src}: {exc}", file=sys.stderr)
        return 1

    rows = _rows(payload)
    violations, coverage = check(rows)

    with (outdir / f"rows-{stamp}.jsonl").open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "stamp": stamp,
        "source": str(src),
        "row_count": len(rows),
        "healthy": not violations,
        "violations": violations,
        "field_coverage": coverage,
        "params": {"min_rows": MIN_ROWS, "min_field_coverage": MIN_FIELD_COVERAGE},
        "elapsed_sec": round(time.time() - started, 3),
    }
    (outdir / f"summary-{stamp}.json").write_text(json.dumps(summary, indent=2))
    (outdir / "summary-latest.json").write_text(json.dumps(summary, indent=2))

    if violations:
        print(f"CONTRACT VIOLATED ({len(rows)} rows):", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        # The diagnosis doubles as the heal prompt; keep it on stdout for the loop.
        print(" ".join(violations))
        return 2

    print(f"contract OK: {len(rows)} rows, all required fields populated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
