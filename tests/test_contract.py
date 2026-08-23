"""Tests for the output contract.

These run without network access: they feed synthetic Scraper Studio payloads through
the validator and assert on the diagnosis, because that diagnosis is what gets sent to
`bdata scraper heal`. A wrong diagnosis produces a wrong repair.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / "scripts" / "validate.py"


def article(i=0, **over):
    row = {
        "title": f"Guidance note {i}",
        "summary": "A summary.",
        "published_date": "2026-08-20",
        "article_url": f"https://rsmus.com/insights/{i}",
        "tags": ["Tax"],
    }
    row.update(over)
    return row


def envelope(url, rows):
    return {"insights": rows, "input": {"url": url}}


def run(payload, tmp_path):
    src = tmp_path / "run.json"
    src.write_text(json.dumps(payload))
    proc = subprocess.run(
        [sys.executable, str(VALIDATE), str(src), str(tmp_path / "out")],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr


def test_healthy_fleet_passes(tmp_path):
    payload = [envelope(f"https://{h}/insights", [article(i) for i in range(5)])
               for h in ("rsmus.com", "www.bdo.com", "www.crowe.com")]
    rc, out, _ = run(payload, tmp_path)
    assert rc == 0, out
    assert "3 sources" in out


def test_empty_source_is_flagged_by_name(tmp_path):
    payload = [
        envelope("https://rsmus.com/insights", [article(i) for i in range(5)]),
        envelope("https://www.bdo.com/insights", []),
    ]
    rc, out, _ = run(payload, tmp_path)
    assert rc == 2
    # The diagnosis must name the source that went empty, so heal knows what to fix.
    assert "bdo.com" in out
    # ...and must not claim the healthy source is broken.
    assert "rsmus.com returned no articles" not in out


def test_missing_title_reports_coverage(tmp_path):
    rows = [article(i, title=None) for i in range(5)]
    rc, out, _ = run([envelope("https://rsmus.com/insights", rows)], tmp_path)
    assert rc == 2
    assert "title" in out and "rsmus.com" in out


def test_partial_dates_are_not_a_break(tmp_path):
    """A firm's listing mixes dated articles with evergreen podcast hubs and eBooks.
    Partial date coverage is normal and must not trigger a heal."""
    rows = [article(i) for i in range(5)] + [article(i, published_date=None) for i in range(5, 9)]
    rc, out, _ = run([envelope("https://www.bdo.com/insights", rows)], tmp_path)
    assert rc == 0, out


def test_dates_missing_everywhere_is_a_break(tmp_path):
    """Near-zero coverage means the date selector stopped matching, which heal can fix."""
    rows = [article(i, published_date=None) for i in range(8)]
    rc, out, _ = run([envelope("https://www.bdo.com/insights", rows)], tmp_path)
    assert rc == 2
    assert "published_date" in out


def test_rows_with_no_title_or_url_are_flagged(tmp_path):
    rows = [article(i) for i in range(5)] + [{"summary": "orphan", "tags": []}]
    rc, out, _ = run([envelope("https://www.bdo.com/insights", rows)], tmp_path)
    assert rc == 2
    assert "neither a title nor a URL" in out


def test_relative_urls_are_flagged(tmp_path):
    rows = [article(i, article_url="/insights/x") for i in range(5)]
    rc, out, _ = run([envelope("https://rsmus.com/insights", rows)], tmp_path)
    assert rc == 2
    assert "relative" in out.lower()


def test_personal_data_fails_the_contract(tmp_path):
    """Author bylines must never be collected; the brief forbids personal data."""
    rows = [article(i, author="A. Person") for i in range(5)]
    rc, out, _ = run([envelope("https://rsmus.com/insights", rows)], tmp_path)
    assert rc == 2
    assert "personal-data" in out or "author" in out


def test_unreadable_input_is_not_heal_worthy(tmp_path):
    src = tmp_path / "broken.json"
    src.write_text("{not json")
    proc = subprocess.run([sys.executable, str(VALIDATE), str(src), str(tmp_path / "o")],
                          capture_output=True, text=True)
    # Exit 1, not 2: heal cannot fix a malformed local file.
    assert proc.returncode == 1


def test_rows_jsonl_records_source_firm(tmp_path):
    payload = [envelope("https://www.bdo.com/insights", [article(i) for i in range(4)])]
    run(payload, tmp_path)
    rows = [json.loads(l) for l in
            next((tmp_path / "out").glob("rows-*.jsonl")).read_text().splitlines() if l.strip()]
    assert {r["_firm"] for r in rows} == {"bdo.com"}
