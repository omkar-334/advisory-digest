#!/usr/bin/env python3
"""Record the outcome of a heal attempt for the published repair log.

    record_heal.py <stamp> <exit-code> [firm] [collector] [diagnosis]

The dashboard renders a repair as "<firm> repaired in place", with the collector id and the
contract's diagnosis. An earlier version wrote only the stamp, exit code and source counts,
so every automatically recorded repair rendered as "Fleet repaired in place · collector
unchanged" with an empty diagnosis, and the control-page verification branch -- keyed off
the firm -- could never fire. The fields the page needs are the fields written here.

Records what measurably changed, not just that a heal ran: a repair can return the same row
count while restoring two fields from 0% to 100%, and a row count alone makes that look like
a no-op.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import SYNTHETIC_FIRMS, read_json

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / "results" / "validate"

USAGE = "usage: record_heal.py <stamp> <exit-code> [firm] [collector] [diagnosis]"


def rows_by_firm(summary) -> dict:
    return {firm: v.get("rows", 0)
            for firm, v in ((summary or {}).get("per_firm") or {}).items()}


def main(argv) -> int:
    if len(argv) < 3:
        print(USAGE, file=sys.stderr)
        return 2

    stamp, run_exit_code = argv[1], argv[2]
    firm = argv[3] if len(argv) > 3 else ""
    collector = argv[4] if len(argv) > 4 else ""
    diagnosis = argv[5] if len(argv) > 5 else ""

    after = read_json(VALIDATE / "summary-latest.json")
    if after is None:
        print(f"no contract summary at {VALIDATE / 'summary-latest.json'}", file=sys.stderr)
        return 1

    # The run immediately before this one is the "before" picture.
    snapshots = sorted(VALIDATE.glob("summary-2*.json"))
    before = read_json(snapshots[-2]) if len(snapshots) >= 2 else {}

    b, a = rows_by_firm(before), rows_by_firm(after)
    metrics = [{"label": f"{name} articles", "before": str(b.get(name, "\u2014")),
                "after": str(a[name])}
               for name in sorted(a) if str(b.get(name)) != str(a[name])]

    event = {
        "stamp": stamp,
        "firm": firm,
        "collector": collector,
        "diagnosis": diagnosis,
        # The control page is a fixture we break on purpose; its repairs are logged
        # separately from repairs to real sources.
        "kind": "verification" if firm in SYNTHETIC_FIRMS else "production",
        "outcome": "repaired" if run_exit_code == "0" else "no_change_needed",
        "resolved": run_exit_code == "0",
        "healthy_sources": after.get("healthy_sources"),
        "sources": after.get("sources"),
        "metrics": metrics,
    }

    out = ROOT / "results" / "heal_loop"
    out.mkdir(parents=True, exist_ok=True)
    (out / "last-event.json").write_text(json.dumps(event, indent=1), encoding="utf-8")
    print(f"recorded heal for {firm or 'fleet'}: resolved={event['resolved']}, "
          f"{len(metrics)} measurement(s) moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
