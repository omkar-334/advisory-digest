#!/usr/bin/env python3
"""Run one newly built collector and record whether it actually returns anything.

    verify_new_source.py <url>

A collector that exists but has never produced a row is not a source. Registering it as
`live` without checking means the next fleet run reports it as broken, with nothing to
distinguish "never worked" from "broke recently". This runs it once, and marks the registry
entry accordingly.

Exits 0 either way: a source that fails verification is recorded, not treated as a build
failure. The point is to keep the registry honest, not to fail the job.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from envfile import load_env

load_env()

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "scripts" / "collectors.json"
BDATA = ROOT / "node_modules" / ".bin" / "bdata"


def host_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def rows_in(payload) -> int:
    envelopes = payload if isinstance(payload, list) else [payload]
    count = 0
    for env in envelopes:
        if not isinstance(env, dict) or env.get("error") or env.get("error_code"):
            continue
        nested = [v for v in env.values()
                  if isinstance(v, list) and v and isinstance(v[0], dict)]
        if nested:
            count += sum(len(group) for group in nested)
        elif env.get("title") or env.get("article_url"):
            count += 1
    return count


def main(argv) -> int:
    if len(argv) < 2:
        print("usage: verify_new_source.py <url>", file=sys.stderr)
        return 2
    url = argv[1]
    firm = host_of(url)

    try:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read the registry: {exc}", file=sys.stderr)
        return 1

    entry = next((c for c in registry["collectors"] if c.get("firm") == firm), None)
    if not entry or not entry.get("collector_id"):
        print(f"no registered collector for {firm}", file=sys.stderr)
        return 1

    out = ROOT / "results" / "verify"
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{firm}.json"

    print(f"verifying {firm} ({entry['collector_id']})")
    subprocess.run(
        [str(BDATA), "scraper", "run", entry["collector_id"], url,
         "--timeout", "600", "--json", "--pretty", "-o", str(target)],
        capture_output=True, text=True,
    )

    try:
        count = rows_in(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        count = 0

    entry["status"] = "live" if count else "unverified"
    entry["verified_rows"] = count
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n")

    if count:
        print(f"::notice::{firm} verified: {count} rows. Added to the fleet.")
    else:
        print(f"::warning::{firm} built but returned no rows. Registered as 'unverified' "
              f"so it is not mistaken for a source that broke later.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
