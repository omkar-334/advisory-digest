#!/usr/bin/env python3
"""Output contract for the advisory-newsroom collector.

This module is the single definition of "healthy scraper output". CI runs it after
every scrape. When it fails, its diagnosis is handed verbatim to `bdata scraper heal`
as the fix prompt, which is what lets the heal loop run without a human in it.

Because one collector runs against many firm newsrooms, the contract is evaluated
per source URL. A single firm redesigning its site fails only its own source, and the
heal prompt names that firm rather than blaming the whole run.

Exit codes:
  0  contract satisfied
  2  contract violated (heal-worthy: the scraper ran but the data is wrong)
  1  hard error (unreadable input: not something heal can repair)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

MIN_ROWS_PER_SOURCE = int(os.environ.get("CONTRACT_MIN_ROWS", "3"))
MIN_FIELD_COVERAGE = float(os.environ.get("CONTRACT_MIN_COVERAGE", "0.7"))
MIN_HEALTHY_SOURCES = float(os.environ.get("CONTRACT_MIN_HEALTHY_SOURCES", "0.6"))

REQUIRED = ("title", "article_url", "published_date")
URL_RE = re.compile(r"^https?://", re.I)
# Author bylines must never be collected; rule 4 of the hackathon brief.
FORBIDDEN_FIELDS = ("author", "author_name", "byline", "email", "phone")


def firm_of(url: str) -> str:
    host = (urlparse(url).hostname or "unknown").lower()
    return host[4:] if host.startswith("www.") else host


def normalise(payload):
    """Flatten Scraper Studio output into (row, source_url) pairs.

    The runner returns one envelope per input URL, with the extracted records nested
    under a generated key ("insights", "articles", ...) that varies per collector
    version. Rather than hardcode that key, take whichever list of objects is present.
    """
    envelopes = payload if isinstance(payload, list) else [payload]
    out = []
    for env in envelopes:
        if not isinstance(env, dict):
            continue
        source = ""
        if isinstance(env.get("input"), dict):
            source = env["input"].get("url") or ""
        source = source or env.get("product_page_url") or env.get("url") or ""

        nested = [v for k, v in env.items()
                  if isinstance(v, list) and v and isinstance(v[0], dict)]
        if nested:
            for group in nested:
                for row in group:
                    out.append((row, source))
        elif any(f in env for f in REQUIRED):
            out.append((env, source))
    return out


def check_source(firm, rows):
    """Contract for one firm's rows. Returns a list of human-readable violations."""
    problems = []
    if len(rows) < MIN_ROWS_PER_SOURCE:
        problems.append(
            f"{firm} returned only {len(rows)} article(s); its listing page always shows "
            f"at least {MIN_ROWS_PER_SOURCE}. The scraper is matching a single card "
            f"instead of iterating over every article on the page."
        )
        if not rows:
            return problems

    for field in REQUIRED:
        present = sum(1 for r in rows if r.get(field) not in (None, "", []))
        if present / len(rows) < MIN_FIELD_COVERAGE:
            problems.append(
                f"On {firm}, '{field}' is empty on {len(rows) - present} of {len(rows)} "
                f"articles ({present / len(rows):.0%} populated). That selector no longer "
                f"matches the page."
            )

    relative = [r["article_url"] for r in rows
                if r.get("article_url") and not URL_RE.match(str(r["article_url"]).strip())]
    if relative:
        problems.append(
            f"On {firm}, {len(relative)} article_url value(s) are relative, e.g. "
            f"{relative[0]!r}. Resolve hrefs to absolute URLs."
        )

    leaked = sorted({f for r in rows for f in FORBIDDEN_FIELDS if r.get(f)})
    if leaked:
        problems.append(
            f"On {firm}, the personal-data fields {leaked} were collected. Remove them: "
            f"only title, summary, published_date, article_url and tags may be extracted."
        )
    return problems


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate.py <run-output.json> [results-dir]", file=sys.stderr)
        return 1

    src, outdir = Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "results/validate")
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = time.time()

    try:
        payload = json.loads(src.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"HARD ERROR: cannot read {src}: {exc}", file=sys.stderr)
        return 1

    pairs = normalise(payload)
    by_firm: dict[str, list] = {}
    for row, source in pairs:
        by_firm.setdefault(firm_of(source), []).append(row)

    per_firm, violations = {}, []
    for firm, rows in sorted(by_firm.items()):
        problems = check_source(firm, rows)
        per_firm[firm] = {"rows": len(rows), "healthy": not problems, "problems": problems}
        violations.extend(problems)

    healthy = sum(1 for v in per_firm.values() if v["healthy"])
    total = len(per_firm) or 1
    fleet_ok = (healthy / total) >= MIN_HEALTHY_SOURCES and bool(pairs)

    with (outdir / f"rows-{stamp}.jsonl").open("w") as fh:
        for row, source in pairs:
            fh.write(json.dumps({**row, "_firm": firm_of(source), "_source": source},
                                ensure_ascii=False) + "\n")

    summary = {
        "stamp": stamp,
        "source": str(src),
        "total_rows": len(pairs),
        "sources": total,
        "healthy_sources": healthy,
        "healthy": fleet_ok and not violations,
        "per_firm": per_firm,
        "params": {
            "min_rows_per_source": MIN_ROWS_PER_SOURCE,
            "min_field_coverage": MIN_FIELD_COVERAGE,
            "min_healthy_sources": MIN_HEALTHY_SOURCES,
        },
        "elapsed_sec": round(time.time() - started, 3),
    }
    (outdir / f"summary-{stamp}.json").write_text(json.dumps(summary, indent=2))
    (outdir / "summary-latest.json").write_text(json.dumps(summary, indent=2))

    if violations:
        print(f"CONTRACT VIOLATED: {healthy}/{total} sources healthy, "
              f"{len(pairs)} rows total", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        # stdout carries the heal prompt.
        print(" ".join(violations[:6]))
        return 2

    print(f"contract OK: {len(pairs)} rows across {total} sources, all healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
