#!/usr/bin/env python3
"""Register any completed collector build into the fleet registry.

Reads the envelopes that `scripts/create_collector.sh` writes and folds the successful
ones into scripts/collectors.json. Keyed on the collector name, so it is safe to re-run
and safe to run while other builds are still in flight.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "scripts" / "collectors.json"

# name prefix -> (firm host, display name, listing url)
KNOWN = {
    "firm-insights":        ("rsmus.com", "RSM", "https://rsmus.com/insights.html"),
    "bdo-insights":         ("bdo.com", "BDO", "https://www.bdo.com/insights"),
    "control-newsroom":     ("advisory-digest.vercel.app", "Control newsroom",
                             "https://advisory-digest.vercel.app/control/insights.html"),
    "crowe-insights":       ("crowe.com", "Crowe", "https://www.crowe.com/insights"),
    "grantthornton-insights": ("grantthornton.com", "Grant Thornton",
                               "https://www.grantthornton.com/insights"),
    "withum-insights":      ("withum.com", "Withum", "https://www.withum.com/resources/"),
    "plantemoran-insights": ("plantemoran.com", "Plante Moran",
                             "https://www.plantemoran.com/explore-our-thinking"),
    "cohnreznick-insights": ("cohnreznick.com", "CohnReznick",
                             "https://www.cohnreznick.com/insights"),
    "marcum-insights":      ("marcumllp.com", "Marcum", "https://www.marcumllp.com/insights"),
    "bakertilly-insights":  ("bakertilly.com", "Baker Tilly",
                             "https://www.bakertilly.com/insights"),
    "cla-insights":         ("claconnect.com", "CLA", "https://www.claconnect.com/en/resources"),
    "eisneramper-insights": ("eisneramper.com", "EisnerAmper",
                             "https://www.eisneramper.com/insights"),
    "pwc-insights":         ("pwc.com", "PwC", "https://www.pwc.com/us/en/library.html"),
}


def main() -> int:
    registry = json.loads(REGISTRY.read_text())
    by_firm = {c["firm"]: c for c in registry["collectors"]}

    for path in sorted(glob.glob(str(ROOT / "results" / "create_collector" / "*.json"))):
        stem = Path(path).stem
        prefix = stem.rsplit("-", 1)[0]
        if prefix not in KNOWN:
            continue
        try:
            env = json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if env.get("status") != "done" or not env.get("collector_id"):
            continue

        firm, display, url = KNOWN[prefix]
        entry = by_firm.get(firm, {})
        # Keep the first working collector for a firm; later rebuilds do not clobber it.
        if entry.get("collector_id"):
            continue
        by_firm[firm] = {"firm": firm, "name": display,
                         "collector_id": env["collector_id"], "url": url, "status": "live"}

    order = [c["firm"] for c in registry["collectors"]]
    merged = [by_firm[f] for f in order if f in by_firm]
    merged += [v for k, v in by_firm.items() if k not in order]
    registry["collectors"] = merged
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n")

    live = [c for c in merged if c.get("collector_id")]
    print(f"{len(live)} live collector(s):")
    for c in live:
        print(f"  {c['name']:18} {c['collector_id']:24} {c['firm']}")
    pending = [c for c in merged if not c.get("collector_id")]
    for c in pending:
        print(f"  {c['name']:18} {'(pending)':24} {c['firm']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
