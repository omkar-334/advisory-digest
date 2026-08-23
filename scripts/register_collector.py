#!/usr/bin/env python3
"""Register a built collector into the fleet registry.

    register_collector.py <envelope.json> <url> <display-name>

Registration is part of building. A collector that exists in Bright Data but not in
scripts/collectors.json is invisible to the fleet, which is how several got lost earlier
in this project.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "scripts" / "collectors.json"


def main(argv) -> int:
    if len(argv) < 4:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    envelope, url, name = Path(argv[1]), argv[2], argv[3]

    if not envelope.exists():
        print("no envelope written", file=sys.stderr)
        return 1
    env = json.loads(envelope.read_text())
    cid, status = env.get("collector_id"), env.get("status")
    if status != "done" or not cid:
        # A poll timeout is not proof of failure: generation often finishes server-side
        # after the CLI stops watching. Say so instead of discarding a working collector.
        print(f"build reported '{status}' (collector {cid}). "
              f"Try running it before rebuilding.", file=sys.stderr)
        return 1

    host = url.split("//", 1)[-1].split("/")[0].lower()
    host = host[4:] if host.startswith("www.") else host

    registry = json.loads(REGISTRY.read_text())
    for c in registry["collectors"]:
        if c["firm"] == host:
            c.update({"collector_id": cid, "url": url, "status": "live"})
            break
    else:
        registry["collectors"].append({"firm": host, "name": name, "collector_id": cid,
                                       "url": url, "status": "live"})
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n")
    print(f"registered {cid} for {host}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
