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

# Always present on a real article card. If either goes missing, the selector broke.
REQUIRED = ("title", "article_url")
# Not every item on a firm's insights listing is a dated article: podcast series hubs,
# eBooks and assessment tools are evergreen and carry no publication date. Partial date
# coverage is therefore normal and is NOT a break. Near-zero coverage is a break, because
# that means the date selector stopped matching everywhere.
DATED_FIELD = "published_date"
MIN_DATED_COVERAGE = float(os.environ.get("CONTRACT_MIN_DATED_COVERAGE", "0.25"))
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
    out, sources = [], []
    # A run can fail for reasons that have nothing to do with the scraper: rate limits,
    # navigation timeouts, a site being briefly down. Those arrive as envelopes carrying
    # an "error" key and no data. They must never be reported as a broken selector,
    # because heal would then be sent to repair a scraper that works.
    errors: dict[str, int] = {}
    for env in envelopes:
        if not isinstance(env, dict):
            continue
        source = ""
        if isinstance(env.get("input"), dict):
            source = env["input"].get("url") or ""
        source = source or env.get("product_page_url") or env.get("url") or ""
        # Record the source even when it yielded nothing. A firm that silently stops
        # returning rows is the exact failure the contract has to catch, and it would
        # be invisible if sources were only discovered through their rows.
        if source:
            sources.append(source)

        if env.get("error") or env.get("error_code"):
            errors[source] = errors.get(source, 0) + 1
            continue

        nested = [v for k, v in env.items()
                  if isinstance(v, list) and v and isinstance(v[0], dict)]
        if nested:
            for group in nested:
                for row in group:
                    out.append((row, source))
        elif any(f in env for f in REQUIRED):
            out.append((env, source))
    return out, sources, errors


def check_source(firm, rows):
    """Contract for one firm's rows. Returns a list of human-readable violations."""
    problems = []
    if not rows:
        return [f"{firm} returned no articles at all. The scraper produced nothing for "
                f"that site, so its article-list selector does not match that firm's "
                f"layout. Make the extraction generic enough to cover it."]
    if len(rows) < MIN_ROWS_PER_SOURCE:
        problems.append(
            f"{firm} returned only {len(rows)} article(s); its listing page always shows "
            f"at least {MIN_ROWS_PER_SOURCE}. The scraper is matching a single card "
            f"instead of iterating over every article on the page."
        )
    for field in REQUIRED:
        present = sum(1 for r in rows if r.get(field) not in (None, "", []))
        if present / len(rows) < MIN_FIELD_COVERAGE:
            problems.append(
                f"On {firm}, '{field}' is empty on {len(rows) - present} of {len(rows)} "
                f"articles ({present / len(rows):.0%} populated). That selector no longer "
                f"matches the page."
            )

    dated = sum(1 for r in rows if r.get(DATED_FIELD) not in (None, "", []))
    if dated / len(rows) < MIN_DATED_COVERAGE:
        problems.append(
            f"On {firm}, '{DATED_FIELD}' is populated on only {dated} of {len(rows)} "
            f"articles ({dated / len(rows):.0%}). Below {MIN_DATED_COVERAGE:.0%} the date "
            f"selector has stopped matching rather than the page simply carrying evergreen "
            f"items. Re-detect the publication date on the article cards."
        )

    relative = [r["article_url"] for r in rows
                if r.get("article_url") and not URL_RE.match(str(r["article_url"]).strip())]
    if relative:
        problems.append(
            f"On {firm}, {len(relative)} article_url value(s) are relative, e.g. "
            f"{relative[0]!r}. Resolve hrefs to absolute URLs."
        )

    # A row with neither a title nor a URL is not an article; it is extraction noise.
    empty_rows = [r for r in rows
                  if not (r.get("title") or "").strip() and not (r.get("article_url") or "").strip()]
    if empty_rows:
        problems.append(
            f"On {firm}, {len(empty_rows)} extracted row(s) have neither a title nor a URL. "
            f"The extraction is matching non-article blocks."
        )

    leaked = sorted({f for r in rows for f in FORBIDDEN_FIELDS if r.get(f)})
    if leaked:
        problems.append(
            f"On {firm}, the personal-data fields {leaked} were collected. Remove them: "
            f"only title, summary, published_date, article_url and tags may be extracted."
        )
    return problems


def heal_prompt(per_firm, limit=1000):
    """Condense per-source violations into one instruction under heal's length cap.

    heal repairs a collector against its own target, so the prompt describes what changed
    on that page. It must not ask one collector to cover unrelated domains: that request
    fails, which we established the expensive way.
    """
    # Only sources that actually ran can be healed. Naming a source whose run failed would
    # send heal to repair a scraper that is fine, which is the most expensive mistake this
    # loop can make: it burns credits and can make a working collector worse.
    empty = sorted(f for f, v in per_firm.items()
                   if v["rows"] == 0 and not v.get("run_failed"))
    other = [p for f, v in per_firm.items() if v["rows"] for p in v["problems"]]

    parts = []
    if empty:
        where = empty[0] if len(empty) == 1 else ", ".join(empty)
        parts.append(
            f"The page layout of {where} has changed and the scraper now returns no "
            f"articles at all. The class names and element nesting it matched on no longer "
            f"exist. Re-detect the repeated article blocks on the current page and extract, "
            f"for each one: title, summary, published_date as ISO 8601, article_url as an "
            f"absolute URL, and tags. Do not extract author names."
        )
    parts.extend(other)

    prompt = " ".join(parts)
    return prompt if len(prompt) <= limit else prompt[:limit - 3].rsplit(" ", 1)[0] + "..."


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate.py <run-output.json> [results-dir] [expected-urls-file]",
              file=sys.stderr)
        return 1

    src, outdir = Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "results/validate")
    # The list of URLs the run was asked to cover. A URL that comes back with no envelope
    # at all produces no rows and no source, so without this it would be invisible to the
    # contract. Silent disappearance is the most dangerous failure mode there is.
    expected = []
    if len(sys.argv) > 3 and Path(sys.argv[3]).exists():
        expected = [l.strip() for l in Path(sys.argv[3]).read_text().splitlines()
                    if l.strip().startswith("http")]
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = time.time()

    try:
        payload = json.loads(src.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"HARD ERROR: cannot read {src}: {exc}", file=sys.stderr)
        return 1

    pairs, sources, envelope_errors = normalise(payload)
    errors_by_firm: dict[str, int] = {}
    for url, count in envelope_errors.items():
        errors_by_firm[firm_of(url)] = errors_by_firm.get(firm_of(url), 0) + count
    # Seed every source that was attempted, so one returning nothing still gets judged.
    by_firm: dict[str, list] = {firm_of(u): [] for u in expected}
    for u in sources:
        by_firm.setdefault(firm_of(u), [])
    for row, source in pairs:
        by_firm.setdefault(firm_of(source), []).append(row)

    per_firm, violations, run_failures = {}, [], []
    seen_firms = {firm_of(u) for u in sources}
    for firm, rows in sorted(by_firm.items()):
        errs = errors_by_firm.get(firm, 0)
        # Two kinds of run failure, neither of which heal can fix:
        #   - the run returned error envelopes (rate limit, navigation timeout)
        #   - the run produced no envelopes at all, so it never reported
        # Two shapes of run failure, neither fixable by heal:
        #   never_reported: the collector produced no envelopes at all, so it never ran
        #   error_dominated: errors outnumber usable rows. A partially rate-limited run
        #     yields a few rows and looks exactly like a scraper that stopped iterating,
        #     so the two have to be told apart by cause rather than by row count.
        never_reported = not rows and firm not in seen_firms
        error_dominated = errs > 0 and errs >= max(len(rows), 1)
        if never_reported or error_dominated:
            detail = ("returned no output at all" if never_reported
                      else f"failed with {errs} error(s) against {len(rows)} usable row(s)")
            run_failures.append(
                f"{firm}: the run {detail}. This is a run failure, not a broken selector, "
                f"so it is not heal-worthy. Re-run before concluding anything about the "
                f"scraper."
            )
            per_firm[firm] = {"rows": len(rows), "healthy": False, "run_failed": True,
                              "errors": max(errs, 0), "problems": []}
            continue

        problems = check_source(firm, rows)
        per_firm[firm] = {"rows": len(rows), "healthy": not problems,
                          "run_failed": False, "errors": errs, "problems": problems}
        violations.extend(problems)

    healthy = sum(1 for v in per_firm.values() if v["healthy"])
    failed_runs = sum(1 for v in per_firm.values() if v.get("run_failed"))
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
        "failed_runs": failed_runs,
        "run_failures": run_failures,
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

    if run_failures:
        print(f"RUN FAILURES on {failed_runs} source(s) (not heal-worthy):", file=sys.stderr)
        for f in run_failures:
            print(f"  ! {f}", file=sys.stderr)

    if violations:
        print(f"CONTRACT VIOLATED: {healthy}/{total} sources healthy, "
              f"{len(pairs)} rows total", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        # stdout carries the heal prompt. `bdata scraper heal` caps it at 1000 chars, so
        # collapse the common case (many firms returning nothing) into one instruction
        # instead of repeating the same sentence per firm.
        print(heal_prompt(per_firm))
        return 2

    if run_failures:
        # Nothing to heal, but the run is not clean either.
        print(f"{len(pairs)} rows across {total - failed_runs} healthy source(s); "
              f"{failed_runs} source(s) failed to run", file=sys.stderr)
        return 1

    print(f"contract OK: {len(pairs)} rows across {total} sources, all healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
