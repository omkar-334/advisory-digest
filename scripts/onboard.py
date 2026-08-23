#!/usr/bin/env python3
"""Self-serve source onboarding: point it at a URL, get a validated collector.

    ./scripts/onboard.py https://www.example-firm.com/insights

The pipeline is deliberately gate-first. Anyone can submit a URL, so eligibility is
decided before a single credit is spent on generating a scraper:

    fetch -> classify (LLM) -> gate -> create collector -> run -> validate -> register

On the gate, three rules are absolute and are enforced here rather than left to judgement:

  government sites   barred by the hackathon rules, and Scraper Studio returns
                     "Domain not allowed" for them anyway
  login walls        barred. We detect and refuse. Nothing here attempts to get past
                     authentication, and nothing here should ever be made to
  paywalls           barred, same reasoning

A 403 to a plain request is NOT a rejection. Several legitimate targets (crowe.com,
marcumllp.com) block naive clients and work perfectly through Bright Data's unblocking
layer, which is the entire point of routing through it. We record the signal and continue.

Stdlib only, so this runs in CI with no install step.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from common import load_env, openai_json

load_env()

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "scripts" / "collectors.json"
RESULTS = ROOT / "results" / "onboard"
USAGE = "usage: onboard.py <listing-page-url> [--dry-run]"

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

GOV_SUFFIXES = (".gov", ".gov.in", ".gov.uk", ".gov.au", ".mil", ".nic.in", ".gouv.fr")
# Below this much visible text there is nothing for the classifier to judge, so it guesses.
# api/check-source.mjs refuses on the same threshold.
MIN_PAGE_TEXT = 200


class TextExtractor(HTMLParser):
    """Pull visible text, skipping script/style, so the classifier sees the page not the code."""

    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.parts.append(text)

    def text(self, limit: int = 6000) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts))[:limit]


def fetch(url: str) -> tuple[int, str, str]:
    """Return (status, html, note). A block is information, not a failure.

    Uses curl rather than urllib because it honours the system trust store, which matters
    wherever TLS is intercepted by a corporate proxy: urllib fails there with
    CERTIFICATE_VERIFY_FAILED on every host.
    """
    proc = subprocess.run(
        ["curl", "-sS", "-L", "--max-time", "25", "-A", UA,
         "-w", "\n%{http_code}", url],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return 0, "", f"could not fetch directly: {proc.stderr.strip()[:160]}"

    body, _, code = proc.stdout.rpartition("\n")
    try:
        status = int(code.strip())
    except ValueError:
        return 0, "", "could not read HTTP status"

    note = ""
    if status in (401, 403, 429):
        note = (f"HTTP {status} to a plain request. Bright Data's unblocking layer often "
                f"handles this, so it is not disqualifying.")
    elif status >= 400:
        note = f"HTTP {status} to a plain request."
    return status, body, note


CLASSIFY_SYSTEM = """You screen candidate web sources for a scraping pipeline that collects
professional and industry articles. You are shown the visible text of one page.

Judge only what the page evidences. Be strict: a wrong "eligible" wastes money generating a
scraper that cannot work, and may breach the project's rules.

Definitions:
- listing page: shows MANY distinct articles/posts, each with its own headline and link.
  A single article, a homepage, a product page or a contact page is NOT a listing page.
- login wall: the content requires signing in or creating an account.
- paywall: the content requires payment or subscription.
- personal data: pages whose primary content is about identifiable private individuals.
  Author bylines alone do not count, since those are excluded at extraction time."""

CLASSIFY_SCHEMA = """{"is_listing_page": bool, "publisher": str, "content_type": str,
"requires_login": bool, "has_paywall": bool, "is_government": bool,
"personal_data_risk": "none"|"low"|"high", "article_count_estimate": int,
"available_fields": [str], "suggested_description": str, "confidence": 0.0-1.0,
"reason": str}"""


def classify(url: str, text: str, status: int) -> dict:
    user = (f"URL: {url}\nHTTP status to a plain request: {status}\n\n"
            f"Visible page text (truncated):\n{text}\n\n"
            f"For suggested_description, write one instruction (max 400 chars) telling an AI "
            f"scraper builder exactly what to extract from each article card on this page. "
            f"Always require title, summary, published_date as ISO 8601, an absolute "
            f"article_url, and tags. Always forbid author names and personal data.")
    return openai_json(CLASSIFY_SYSTEM, user, CLASSIFY_SCHEMA)


def gate(url: str, verdict: dict) -> list[str]:
    """Absolute rejections. Returns the reasons; empty means eligible."""
    host = (urlparse(url).hostname or "").lower()
    blocked = []

    if verdict.get("is_government") or any(host.endswith(s) for s in GOV_SUFFIXES):
        blocked.append("government site: barred by the hackathon rules, and Scraper Studio "
                       "rejects these domains with 'Domain not allowed'")
    if verdict.get("requires_login"):
        blocked.append("content is behind a login: barred, and this pipeline will not "
                       "attempt to authenticate")
    if verdict.get("has_paywall"):
        blocked.append("content is paywalled: barred")
    if verdict.get("personal_data_risk") == "high":
        blocked.append("page is primarily about identifiable private individuals")
    if not verdict.get("is_listing_page"):
        blocked.append(f"not an article listing page (looks like "
                       f"{verdict.get('content_type', 'something else')})")
    return blocked


def slug(url: str) -> str:
    host = (urlparse(url).hostname or "source").lower().removeprefix("www.")
    return re.sub(r"[^a-z0-9]+", "-", host.split(".")[0]).strip("-") or "source"


def register(firm: str, name: str, collector_id: str, url: str) -> None:
    """Upsert one collector into the fleet registry, keyed by firm.

    Mirrors register_collector.py, which does the same for the shell path. A collector
    that exists in Bright Data but not here is invisible to the fleet.
    """
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(registry, dict):
        raise ValueError(f"{REGISTRY} is not a fleet registry")
    collectors = registry.setdefault("collectors", [])
    for c in collectors:
        if c.get("firm") == firm:
            c.update({"collector_id": collector_id, "url": url, "status": "live"})
            break
    else:
        collectors.append({"firm": firm, "name": name, "collector_id": collector_id,
                           "url": url, "status": "live"})
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def main(argv) -> int:
    urls = [a for a in argv[1:] if not a.startswith("-")]
    if not urls:
        print(USAGE, file=sys.stderr)
        return 1
    url = urls[0]
    if not re.match(r"^https?://", url, re.I):
        print(f"{USAGE}\nnot a URL: {url!r}", file=sys.stderr)
        return 1
    dry_run = "--dry-run" in argv
    RESULTS.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] fetching {url}")
    status, html, note = fetch(url)
    if note:
        print(f"      {note}")
    if not html.strip():
        print("      nothing to classify; aborting", file=sys.stderr)
        return 1

    parser = TextExtractor()
    parser.feed(html)
    text = parser.text()
    if len(text) < MIN_PAGE_TEXT:
        print("      page returned almost no readable text; aborting", file=sys.stderr)
        return 1

    print(f"[2/5] classifying with {OPENAI_MODEL}")
    try:
        verdict = classify(url, text, status)
    except RuntimeError as exc:
        print(f"      {exc}", file=sys.stderr)
        return 1
    print(f"      publisher: {verdict.get('publisher')}")
    print(f"      type: {verdict.get('content_type')} | "
          f"~{verdict.get('article_count_estimate')} articles | "
          f"confidence {verdict.get('confidence')}")

    blocked = gate(url, verdict)
    report = {"url": url, "http_status": status, "verdict": verdict, "blocked": blocked}
    (RESULTS / f"{slug(url)}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if blocked:
        print("[3/5] REJECTED")
        for b in blocked:
            print(f"      - {b}")
        return 2
    print("[3/5] eligible")

    description = (verdict.get("suggested_description") or "").strip()[:500]
    if not description:
        print("      classifier returned no description; aborting", file=sys.stderr)
        return 1
    print(f"      description: {description[:110]}...")

    if dry_run:
        print("[4/5] dry run, not creating a collector")
        return 0

    name = f"{slug(url)}-insights"
    builder = ROOT / "scripts" / "create_collector.sh"
    if not builder.exists():
        print(f"      missing {builder}", file=sys.stderr)
        return 1

    print(f"[4/5] building collector '{name}' (this takes several minutes)")
    proc = subprocess.run([str(builder), name, url, description],
                          capture_output=True, text=True)
    envelopes = sorted((ROOT / "results" / "create_collector").glob(f"{name}-*.json"))
    if not envelopes:
        print(f"      build produced no envelope\n{proc.stdout[-400:]}", file=sys.stderr)
        return 1
    try:
        env = json.loads(envelopes[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"      cannot read {envelopes[-1]}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(env, dict):
        print(f"      {envelopes[-1]} is not a build envelope", file=sys.stderr)
        return 1
    cid = env.get("collector_id")
    if env.get("status") != "done" or not cid:
        # A poll timeout is not proof of failure: generation often completes server-side
        # after the CLI stops watching. Say so rather than discarding a working collector.
        print(f"      build reported '{env.get('status')}' (collector {cid}). "
              f"Try running it before rebuilding.", file=sys.stderr)
        return 1

    print(f"[5/5] registering {cid}")
    try:
        register((urlparse(url).hostname or "").lower().removeprefix("www."),
                 verdict.get("publisher") or slug(url).title(), cid, url)
    except (OSError, ValueError) as exc:
        # The collector exists and cost several minutes to build. Print what it would
        # take to register it by hand rather than losing it to a registry problem.
        print(f"      could not update {REGISTRY}: {exc}\n"
              f"      add it manually: collector_id={cid} url={url}", file=sys.stderr)
        return 1
    print("      done. Run ./scripts/run_fleet.sh to validate it against the contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
