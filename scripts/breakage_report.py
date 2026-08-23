#!/usr/bin/env python3
"""Write a human-readable report of sources that are genuinely broken.

Prints nothing when there is nothing to report, so a caller can treat empty output as
"no alert needed". Sources whose RUN failed are excluded: they are not broken, and paging
someone about a rate limit trains them to ignore the alert.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    summary_path = ROOT / "results" / "validate" / "summary-latest.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0

    lines = []
    for firm, v in sorted((summary.get("per_firm") or {}).items()):
        if v.get("healthy") or v.get("run_failed"):
            continue
        problems = "; ".join(v.get("problems") or []) or "no detail recorded"
        lines.append(f"- **{firm}** ({v.get('rows', 0)} rows): {problems}")

    if not lines:
        return 0

    failed = summary.get("failed_runs", 0)
    print("The scheduled run repaired what it could. These sources still fail the contract:")
    print()
    print("\n".join(lines))
    if failed:
        print()
        print(f"_{failed} further source(s) could not run at all. Those are not broken "
              f"scrapers and were not sent for repair._")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
