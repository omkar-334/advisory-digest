#!/usr/bin/env python3
"""Record the outcome of a heal attempt for the published repair log.

    record_heal.py <stamp> <exit-code-of-the-verifying-run>

Records what measurably changed, not just that a heal ran. A repair that returns the same
number of rows can still have restored two fields from 0% to 100%, and a row count alone
makes that look like a no-op.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / "results" / "validate"
HEAL_LOOP = ROOT / "results" / "heal_loop"
USAGE = "usage: record_heal.py <stamp> <exit-code-of-the-verifying-run>"


def read_summary(path: Path) -> dict:
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return {}
    return summary if isinstance(summary, dict) else {}


def coverage(summary: dict) -> dict[str, int]:
    """Rows per firm, which is what the timeline compares before and after a repair."""
    return {firm: v.get("rows", 0)
            for firm, v in (summary.get("per_firm") or {}).items()
            if isinstance(v, dict)}


def main(argv) -> int:
    if len(argv) < 3:
        print(USAGE, file=sys.stderr)
        return 2
    stamp, run_exit_code = argv[1], argv[2]

    after_path = VALIDATE / "summary-latest.json"
    if not after_path.exists():
        print(f"no contract summary at {after_path}", file=sys.stderr)
        return 1
    after = read_summary(after_path)
    if not after:
        return 1

    # summary-latest.json is a copy of the newest stamped summary, so the run immediately
    # before this one is the second-newest: index -2, not -1.
    snapshots = sorted(VALIDATE.glob("summary-2*.json"))
    before = read_summary(snapshots[-2]) if len(snapshots) >= 2 else {}

    b, a = coverage(before), coverage(after)
    metrics = [{"label": f"{firm} articles",
                "before": str(b.get(firm, "—")), "after": str(a[firm])}
               for firm in sorted(a) if str(b.get(firm)) != str(a[firm])]

    resolved = run_exit_code == "0"
    HEAL_LOOP.mkdir(parents=True, exist_ok=True)
    (HEAL_LOOP / "last-event.json").write_text(json.dumps({
        "stamp": stamp,
        "resolved": resolved,
        "healthy_sources": after.get("healthy_sources"),
        "sources": after.get("sources"),
        "metrics": metrics,
    }, indent=1), encoding="utf-8")
    print(f"recorded heal outcome: resolved={resolved}, {len(metrics)} measurement(s) moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
