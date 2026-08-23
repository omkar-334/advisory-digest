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
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "scripts" / "collectors.json"
USAGE = "usage: register_collector.py <envelope.json> <url> <display-name>"


def main(argv) -> int:
    if len(argv) < 4:
        print(USAGE, file=sys.stderr)
        return 2
    envelope, url, name = Path(argv[1]), argv[2], argv[3]

    if not envelope.exists():
        print("no envelope written", file=sys.stderr)
        return 1
    try:
        env = json.loads(envelope.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {envelope}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(env, dict):
        print(f"{envelope} is not a build envelope", file=sys.stderr)
        return 1

    cid, status = env.get("collector_id"), env.get("status")
    if status != "done" or not cid:
        # A poll timeout is not proof of failure: generation often finishes server-side
        # after the CLI stops watching. Say so instead of discarding a working collector.
        print(f"build reported '{status}' (collector {cid}). "
              f"Try running it before rebuilding.", file=sys.stderr)
        return 1

    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not host:
        print(f"cannot read a hostname from {url!r}", file=sys.stderr)
        return 2

    registry = None
    try:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {REGISTRY}: {exc}", file=sys.stderr)
    if not isinstance(registry, dict):
        # The collector exists in Bright Data whatever happens here, so name it: the
        # operator can add the entry by hand rather than pay to rebuild it.
        print(f"cannot use {REGISTRY} as a fleet registry. "
              f"Add this by hand: firm={host} collector_id={cid} url={url}",
              file=sys.stderr)
        return 1

    collectors = registry.setdefault("collectors", [])
    for c in collectors:
        if c.get("firm") == host:
            c.update({"collector_id": cid, "url": url, "status": "live"})
            break
    else:
        collectors.append({"firm": host, "name": name, "collector_id": cid,
                           "url": url, "status": "live"})
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(f"registered {cid} for {host}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
