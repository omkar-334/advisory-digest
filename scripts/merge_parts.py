#!/usr/bin/env python3
"""Merge per-collector run output into one payload for the contract.

    merge_parts.py <output.json> <part.json> [part.json ...]

Each collector writes its own file so runs can proceed concurrently and be resumed. The
contract needs to see the whole fleet at once to judge coverage, so they are combined here.
A part that is missing or malformed is skipped and reported rather than aborting the merge:
one bad file should not discard twelve good ones.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv) -> int:
    if len(argv) < 3:
        print("usage: merge_parts.py <output.json> <part.json> [...]", file=sys.stderr)
        return 2

    out = Path(argv[1])
    merged, skipped = [], []
    for path in argv[2:]:
        try:
            data = json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            skipped.append(f"{Path(path).name}: {exc}")
            continue
        merged.extend(data if isinstance(data, list) else [data])

    out.write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    print(f"merged {len(merged)} envelopes from {len(argv) - 2 - len(skipped)} collector(s)")
    for s in skipped:
        print(f"  skipped {s}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
