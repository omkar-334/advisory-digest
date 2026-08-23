#!/usr/bin/env python3
"""Shared helpers for the pipeline scripts.

These live in one place because the alternative already cost us a bug. The definition of
"is this a real source" was copied into three scripts; excluding the control-page fixture
from two of them still left it being served through the third. A rule that is written down
three times is three rules.

Stdlib only, by design: everything here runs in CI with no install step.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# docs/control/insights.html is a fixture we break on purpose to prove self-healing. Its
# articles are invented, so it must never count as coverage or reach a reader. Defined once,
# consumed everywhere.
SYNTHETIC_FIRMS = {"advisory-digest.vercel.app"}

# Author bylines and contact details are excluded at extraction time; this is the list the
# contract checks against and the publisher strips again before anything is served.
FORBIDDEN_FIELDS = ("author", "author_name", "byline", "email", "phone")


def load_env(path: Path | None = None) -> None:
    """Load .env into os.environ, without overriding real environment variables.

    The shell scripts source .env before running anything. A Python script invoked directly
    -- from CI, from cron, or by hand -- does not get that, and then fails with "KEY is not
    set" while the key sits in a file two directories up.
    """
    try:
        text = (path or ROOT / ".env").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def read_json(path: Path, default=None):
    """Read JSON, returning `default` if it is missing or unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def parse_date(value):
    """Parse a published date into an aware datetime, or None.

    Collectors emit dates in several shapes and sometimes emit nulls, so this never raises:
    an unparseable date is absent, not fatal.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    for parse in (datetime.fromisoformat,
                  lambda t: datetime.strptime(t[:10], "%Y-%m-%d")):
        try:
            dt = parse(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def firm_of(row) -> str:
    """The host a row came from. Never None, so it is safe to sort and group on."""
    if not isinstance(row, dict):
        return "unknown"
    return (row.get("_firm") or "").strip() or "unknown"


def is_real_firm(firm) -> bool:
    """False for the control-page fixture and for anything unattributed."""
    return bool(firm) and firm not in SYNTHETIC_FIRMS and firm != "unknown"


def real_rows(rows):
    """Drop rows that did not come from a real source."""
    return [r for r in rows if is_real_firm(firm_of(r))]


def openai_json(system: str, user: str, schema: str, *, timeout: int = 120) -> dict:
    """Ask the model for a JSON object, and fail loudly if it does not return one.

    Uses curl rather than urllib because it honours the system trust store, which matters
    wherever TLS is intercepted by a corporate proxy: urllib fails there with
    CERTIFICATE_VERIFY_FAILED against every host.
    """
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": f"{system}\n\nReturn JSON only: {schema}"},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    proc = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout),
         "https://api.openai.com/v1/chat/completions",
         "-H", f"Authorization: Bearer {key}",
         "-H", "Content-Type: application/json", "-d", "@-"],
        input=json.dumps(payload), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"OpenAI request failed: {proc.stderr.strip()[:200]}")
    try:
        body = json.loads(proc.stdout)
    except ValueError as exc:
        raise RuntimeError(f"OpenAI returned unreadable output: {exc}") from exc
    if "error" in body:
        raise RuntimeError(f"OpenAI error: {body['error'].get('message', '')[:200]}")
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected OpenAI response shape: {exc}") from exc

    # Outside a try, a malformed reply raises ValueError, which callers do not catch --
    # so one bad response aborts a whole run instead of skipping one item.
    try:
        parsed = json.loads(content)
    except ValueError as exc:
        raise RuntimeError(f"model did not return valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("model did not return a JSON object")
    return parsed
