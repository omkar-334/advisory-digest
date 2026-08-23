#!/usr/bin/env python3
"""Load .env into the process environment.

The shell scripts source .env before running anything. A Python script invoked directly --
from CI, from a cron, or by hand -- does not get that, and then fails with "KEY is not set"
while the key is sitting in a file two directories up. Rather than making every caller
remember to source it, each script that needs credentials loads them itself.

Real environment variables always win, so CI secrets and a local .env can coexist.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    env_path = path or (ROOT / ".env")
    try:
        text = env_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # An exported value may be quoted; a real environment variable is authoritative.
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
