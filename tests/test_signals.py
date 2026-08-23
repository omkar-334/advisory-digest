"""Tests for cross-firm signal detection.

The claim the whole product rests on is "N independent firms covered this". If that count is
wrong the product is worse than useless, so the counting rules are pinned here.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGNALS = ROOT / "scripts" / "signals.py"


def run_signals(tmp_path, rows, topics=None):
    docs = tmp_path / "docs" / "data"
    docs.mkdir(parents=True)
    (docs / "latest.json").write_text(json.dumps(rows))
    if topics is not None:
        (docs / "topics.json").write_text(json.dumps(topics))
    (tmp_path / "scripts").mkdir(exist_ok=True)
    shim = tmp_path / "scripts" / "signals.py"
    shim.write_text(SIGNALS.read_text())
    proc = subprocess.run([sys.executable, str(shim)], capture_output=True, text=True,
                          cwd=str(tmp_path))
    out = docs / "signals.json"
    return proc.returncode, (json.loads(out.read_text()) if out.exists() else None), proc.stderr


def article(firm, url, title="Section 174 guidance", date="2026-08-20", **over):
    row = {"title": title, "summary": "", "published_date": date,
           "article_url": url, "tags": [], "_firm": firm}
    row.update(over)
    return row


def topics_for(mapping, labels):
    return {"model": "test", "topics": labels, "assignments": mapping}


def test_one_firm_publishing_repeatedly_is_not_a_signal(tmp_path):
    """Marketing, not a development. The threshold is distinct firms, not article count."""
    rows = [article("rsmus.com", f"https://rsmus.com/{i}") for i in range(6)]
    mapping = {r["article_url"]: ["Section 174"] for r in rows}
    rc, out, _ = run_signals(tmp_path, rows, topics_for(mapping, ["Section 174"]))
    assert rc == 0
    assert out["signals"] == [], "a single firm must never produce a signal"


def test_two_firms_each_publishing_once_is_a_signal(tmp_path):
    rows = [article("rsmus.com", "https://rsmus.com/1"),
            article("bdo.com", "https://bdo.com/1")]
    mapping = {r["article_url"]: ["Section 174"] for r in rows}
    rc, out, _ = run_signals(tmp_path, rows, topics_for(mapping, ["Section 174"]))
    assert rc == 0
    assert len(out["signals"]) == 1
    assert out["signals"][0]["firms"] == 2


def test_signals_are_ranked_by_breadth_not_volume(tmp_path):
    rows = ([article("rsmus.com", f"https://rsmus.com/n{i}") for i in range(8)] +
            [article("bdo.com", "https://bdo.com/n")] +
            [article(f"firm{i}.com", f"https://firm{i}.com/w") for i in range(4)])
    mapping = {r["article_url"]: (["Narrow"] if "rsmus" in r["article_url"] or "bdo" in r["article_url"]
                                  else ["Wide"]) for r in rows}
    rc, out, _ = run_signals(tmp_path, rows, topics_for(mapping, ["Narrow", "Wide"]))
    assert rc == 0
    # Narrow has 9 articles across 2 firms; Wide has 4 across 4. Breadth wins.
    assert out["signals"][0]["topic"] == "Wide"


def test_future_dated_items_do_not_move_the_window(tmp_path):
    """Firms post registration pages for upcoming webinars; those must not set 'as of'."""
    rows = [article("rsmus.com", "https://rsmus.com/1", date="2026-08-20"),
            article("bdo.com", "https://bdo.com/1", date="2027-12-31")]
    mapping = {r["article_url"]: ["Section 174"] for r in rows}
    rc, out, _ = run_signals(tmp_path, rows, topics_for(mapping, ["Section 174"]))
    assert rc == 0
    assert not out["as_of"].startswith("2027"), f"future date leaked into as_of: {out['as_of']}"


def test_null_firm_does_not_crash(tmp_path):
    """Scraped rows carry nulls everywhere; a missing _firm must not take the run down."""
    rows = [article("rsmus.com", "https://rsmus.com/1"),
            article(None, "https://unknown/1"),
            article("bdo.com", "https://bdo.com/1")]
    mapping = {r["article_url"]: ["Section 174"] for r in rows}
    rc, out, err = run_signals(tmp_path, rows, topics_for(mapping, ["Section 174"]))
    assert rc == 0, err


def test_empty_dataset_is_reported_not_crashed(tmp_path):
    rc, out, err = run_signals(tmp_path, [])
    assert rc == 1
    assert "empty" in err.lower()
