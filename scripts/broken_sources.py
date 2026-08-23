#!/usr/bin/env python3
"""Emit the sources that are genuinely heal-worthy, as TSV for the heal loop.

Columns: collector_id, url, firm, diagnosis

A source is emitted only if the contract found a real defect. Sources whose RUN failed are
excluded: their output is empty for reasons the scraper cannot fix, and healing them spends
credits repairing something that works.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    summary_path = ROOT / "results" / "validate" / "summary-latest.json"
    if not summary_path.exists():
        print("no contract summary", file=sys.stderr)
        return 1
    summary = json.loads(summary_path.read_text())
    registry = json.loads((ROOT / "scripts" / "collectors.json").read_text())["collectors"]
    by_firm = {c["firm"]: c for c in registry if c.get("collector_id")}

    for firm, v in sorted(summary.get("per_firm", {}).items()):
        if v.get("healthy") or v.get("run_failed"):
            continue
        entry = by_firm.get(firm)
        if not entry:
            print(f"no collector registered for {firm}", file=sys.stderr)
            continue
        # heal caps the prompt at 1000 characters.
        diagnosis = " ".join(v.get("problems") or [])[:900]
        if diagnosis:
            print("\t".join([entry["collector_id"], entry["url"], firm, diagnosis]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
