#!/usr/bin/env python3
"""Emit the sources that are genuinely heal-worthy, as TSV for the heal loop.

Columns: collector_id, url, firm, diagnosis

A source is emitted only if the contract found a real defect. Sources whose RUN failed are
excluded: their output is empty for reasons the scraper cannot fix, and healing them spends
credits repairing something that works.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = ROOT / "results" / "validate" / "summary-latest.json"
REGISTRY = ROOT / "scripts" / "collectors.json"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return None


def main() -> int:
    if not SUMMARY.exists():
        print("no contract summary", file=sys.stderr)
        return 1
    summary = read_json(SUMMARY)
    registry = read_json(REGISTRY)
    if not isinstance(summary, dict) or not isinstance(registry, dict):
        return 1

    # A firm can only be healed if it has both an id to heal and a URL to re-run against.
    by_firm = {c["firm"]: c for c in registry.get("collectors") or []
               if isinstance(c, dict) and c.get("firm")
               and c.get("collector_id") and c.get("url")}

    for firm, v in sorted((summary.get("per_firm") or {}).items()):
        if v.get("healthy") or v.get("run_failed"):
            continue
        entry = by_firm.get(firm)
        if not entry:
            print(f"no runnable collector registered for {firm}", file=sys.stderr)
            continue
        # The heal loop reads these lines with `IFS=$'\t' read`, so any tab or newline
        # inside a diagnosis would shift every column after it. heal caps the prompt at
        # 1000 characters, hence the trim.
        problems = " ".join(str(p) for p in v.get("problems") or [])
        diagnosis = re.sub(r"\s+", " ", problems).strip()[:900]
        if diagnosis:
            print("\t".join([entry["collector_id"], entry["url"], firm, diagnosis]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
