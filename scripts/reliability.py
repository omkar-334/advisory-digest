#!/usr/bin/env python3
"""Score each source on how reliably it can be scraped.

This is a byproduct of self-healing that nobody else has. Running a repairing collector
against a dozen enterprise CMSs for a week produces a record of which websites are hostile
to extraction: which broke, how they broke, which repairs held, and which sources have never
worked at all. That is operational intelligence about the web itself, and it exists only
because the pipeline keeps a contract and logs every repair attempt.

Reads docs/data/heals.json (the incident record) and docs/data/health.json (current
contract state). No scraping, no model call.

Writes docs/data/reliability.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import read_json

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "data"

# A source is graded on what actually happened to it, not on a subjective score. The order
# here is the order of severity, worst first.
GRADES = {
    "never_worked": ("Never worked", "No run has produced a row. The collector exists; the "
                                     "site has never yielded data."),
    "repaired": ("Repaired", "Broke and was fixed in place. The collector ID never changed."),
    "false_alarm": ("Contract was wrong", "Flagged as broken, but the scraper was fine and "
                                          "the contract had to be corrected."),
    "stable": ("Stable", "Has never needed a repair."),
}


def main() -> int:
    incidents = read_json(DOCS / "heals.json", [])
    health = read_json(DOCS / "health.json")
    registry = read_json(ROOT / "scripts" / "collectors.json", {})

    if health is None:
        print("no contract report; run the fleet first", file=sys.stderr)
        return 1

    collectors = [c for c in (registry.get("collectors") or []) if c.get("collector_id")]
    per_firm = health.get("per_firm") or {}

    sources = []
    for c in collectors:
        firm = c["firm"]
        mine = [i for i in incidents if i.get("firm") == firm]
        state = per_firm.get(firm, {})

        repairs = [i for i in mine if i.get("outcome") == "repaired"]
        false_alarms = [i for i in mine if i.get("outcome") == "no_change_needed"]
        failures = [i for i in mine if i.get("outcome") == "failed"]

        # Grade on evidence, worst first.
        if failures and not repairs and not state.get("rows"):
            grade = "never_worked"
        elif repairs:
            grade = "repaired"
        elif false_alarms:
            grade = "false_alarm"
        else:
            grade = "stable"

        sources.append({
            "firm": firm,
            "name": c.get("name") or firm,
            "collector_id": c["collector_id"],
            "rows": state.get("rows", 0),
            "healthy": bool(state.get("healthy")),
            "run_failed": bool(state.get("run_failed")),
            "repairs": len(repairs),
            "false_alarms": len(false_alarms),
            "failures": len(failures),
            "grade": grade,
            "grade_label": GRADES[grade][0],
            "grade_note": GRADES[grade][1],
            "incidents": [
                {"stamp": i.get("stamp"), "outcome": i.get("outcome"),
                 "diagnosis": i.get("diagnosis"), "resolution": i.get("resolution")}
                for i in mine
            ],
        })

    # Fleet-level incidents belong to no single source but are the most instructive ones.
    fleet = [i for i in incidents if i.get("firm") == "fleet"]

    by_grade = {}
    for s in sources:
        by_grade[s["grade"]] = by_grade.get(s["grade"], 0) + 1

    out = {
        "sources": sorted(sources, key=lambda s: (s["grade"] != "never_worked",
                                                  -s["repairs"], s["name"])),
        "fleet_incidents": fleet,
        "totals": {
            "collectors": len(collectors),
            "working": sum(1 for s in sources if s["rows"]),
            "repairs_that_held": sum(s["repairs"] for s in sources),
            "false_alarms": sum(s["false_alarms"] for s in sources),
            "never_worked": by_grade.get("never_worked", 0),
            "stable": by_grade.get("stable", 0),
        },
        "grades": {k: {"label": v[0], "note": v[1]} for k, v in GRADES.items()},
    }
    (DOCS / "reliability.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    t = out["totals"]
    print(f"{t['collectors']} collectors: {t['stable']} never needed repair, "
          f"{t['repairs_that_held']} repaired, {t['false_alarms']} false alarm(s), "
          f"{t['never_worked']} never worked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
