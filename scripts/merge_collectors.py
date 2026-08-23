#!/usr/bin/env python3
"""Fold collector build results into the fleet registry.

Parallel builds each write their own results file so they never contend for
scripts/collectors.json. This merges them in, keyed on firm, and leaves anything
already registered untouched unless the new entry has a real collector id.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "scripts" / "collectors.json"


def main() -> int:
    registry = json.loads(REGISTRY.read_text())
    by_firm = {c["firm"]: c for c in registry["collectors"]}

    added, updated, failed = [], [], []
    for path in sorted(glob.glob(str(ROOT / "results" / "subagent-batch-*.json"))):
        try:
            entries = json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"skipping {path}: {exc}", file=sys.stderr)
            continue

        for e in entries:
            firm = (e.get("firm") or "").strip()
            cid = (e.get("collector_id") or "").strip()
            if not firm:
                continue
            if not cid:
                failed.append((firm, e.get("error", "")[:80]))
                continue

            entry = {
                "firm": firm,
                "name": e.get("name") or firm,
                "collector_id": cid,
                "url": e.get("url", ""),
                "status": e.get("status") or "live",
            }
            if firm in by_firm:
                if by_firm[firm].get("collector_id") != cid:
                    by_firm[firm].update(entry)
                    updated.append(firm)
            else:
                by_firm[firm] = entry
                added.append(firm)

    order = [c for c in registry["collectors"] if c["firm"] in by_firm]
    seen = {c["firm"] for c in order}
    merged = [by_firm[c["firm"]] for c in order]
    merged += [v for k, v in by_firm.items() if k not in seen]
    registry["collectors"] = merged
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n")

    live = [c for c in merged if c.get("collector_id")]
    print(f"registry: {len(live)} live collector(s); added {len(added)}, updated {len(updated)}")
    for f in added:
        print(f"  + {f}")
    for f, err in failed:
        print(f"  ! {f} failed: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
