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


def coverage(summary):
    return {f: v.get("rows", 0) for f, v in (summary.get("per_firm") or {}).items()}


def main(argv) -> int:
    if len(argv) < 3:
        return 2
    stamp, rc = argv[1], argv[2]
    after_path = VALIDATE / "summary-latest.json"
    if not after_path.exists():
        return 1
    after = json.loads(after_path.read_text())

    # The run immediately before this one is the "before" picture.
    snapshots = sorted(VALIDATE.glob("summary-2*.json"))
    before = json.loads(snapshots[-2].read_text()) if len(snapshots) >= 2 else {}

    b, a = coverage(before), coverage(after)
    metrics = [{"label": f"{f} articles", "before": str(b.get(f, "—")), "after": str(a[f])}
               for f in sorted(a) if str(b.get(f)) != str(a[f])]

    (ROOT / "results" / "heal_loop").mkdir(parents=True, exist_ok=True)
    (ROOT / "results" / "heal_loop" / "last-event.json").write_text(json.dumps({
        "stamp": stamp,
        "resolved": rc == "0",
        "healthy_sources": after.get("healthy_sources"),
        "sources": after.get("sources"),
        "metrics": metrics,
    }, indent=1))
    print(f"recorded heal outcome: resolved={rc == '0'}, {len(metrics)} measurement(s) moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
