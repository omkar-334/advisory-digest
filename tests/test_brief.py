"""Tests for lead-lag, which is arithmetic and must not invent findings.

The brief text itself is a model call and is not unit-tested. The lead-lag claim is not:
"RSM published first, six days ahead" is a factual assertion the page makes, and an early
version of it reported leads of 439 days simply because the archive reached back that far.
"""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("brief", ROOT / "scripts" / "brief.py")
brief = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brief)

BASE = datetime(2026, 8, 1, tzinfo=timezone.utc)


def art(firm, day_offset, title="A note"):
    return {"_firm": firm, "title": title,
            "published_date": (BASE + timedelta(days=day_offset)).date().isoformat(),
            "article_url": f"https://{firm}/{day_offset}"}


def test_a_single_firm_has_no_lead():
    """You cannot lead a field of one."""
    assert brief.lead_lag([art("rsmus.com", 0), art("rsmus.com", 3)]) is None


def test_two_firms_are_not_enough_for_a_burst():
    """Two firms writing about a perennial subject is not a reaction to an event."""
    assert brief.lead_lag([art("rsmus.com", 0), art("bdo.com", 2)]) is None


def test_three_firms_close_together_is_a_burst():
    lead = brief.lead_lag([art("rsmus.com", 0), art("bdo.com", 3), art("crowe.com", 5)])
    assert lead is not None
    assert lead["first_firm"] == "rsmus.com"
    assert lead["lead_days"] == 3
    assert lead["burst_firms"] == 3


def test_articles_spread_across_a_year_are_not_a_burst():
    """The failure this was written for: 439-day 'leads' that were just old coverage."""
    spread = [art("rsmus.com", 0), art("bdo.com", 200), art("crowe.com", 400)]
    assert brief.lead_lag(spread) is None


def test_an_old_article_does_not_steal_the_lead_from_a_real_burst():
    articles = [art("rsmus.com", 0)] + [art("bdo.com", 300), art("crowe.com", 305),
                                        art("claconnect.com", 310)]
    lead = brief.lead_lag(articles)
    assert lead is not None
    assert lead["first_firm"] == "bdo.com", "the burst, not the archive, defines the lead"
    assert lead["lead_days"] == 5


def test_undated_articles_are_ignored_not_guessed():
    articles = [art("rsmus.com", 0), art("bdo.com", 2), art("crowe.com", 4),
                {"_firm": "withum.com", "title": "No date", "published_date": None}]
    lead = brief.lead_lag(articles)
    assert lead is not None
    assert "withum.com" not in lead["followers"]


def test_the_control_page_is_not_a_firm():
    """Our own fixture must never count as coverage or the consensus claim becomes false."""
    assert brief.is_real_firm("rsmus.com")
    assert not brief.is_real_firm("advisory-digest.vercel.app")
    assert not brief.is_real_firm("")
    assert not brief.is_real_firm(None)


def test_refresh_drops_a_subject_that_is_no_longer_cross_firm(tmp_path, monkeypatch):
    """A brief's prose claims agreement between firms. If the dataset changes so that only
    one firm remains, the text is no longer true and the brief must go rather than sit there
    with a stale count.
    """
    import json
    docs = tmp_path / "docs" / "data"
    docs.mkdir(parents=True)
    (docs / "briefs.json").write_text(json.dumps({"model": "test", "briefs": [
        {"topic": "Still broad", "firms": 9, "firm_list": ["old"], "articles": 9,
         "consensus": "x"},
        {"topic": "Now narrow", "firms": 5, "firm_list": ["old"], "articles": 5,
         "consensus": "y"},
    ]}))
    monkeypatch.setattr(brief, "DOCS", docs)

    rows = [art("rsmus.com", 0), art("bdo.com", 1), art("crowe.com", 2),
            art("withum.com", 3)]
    assignments = {r["article_url"]: ["Still broad"] for r in rows}
    assignments[art("claconnect.com", 4)["article_url"]] = ["Now narrow"]
    rows.append(art("claconnect.com", 4))

    assert brief.refresh_counts(rows, assignments) == 0
    out = json.loads((docs / "briefs.json").read_text())
    topics = [b["topic"] for b in out["briefs"]]
    assert topics == ["Still broad"], "a single-firm subject must not remain a brief"
    assert out["briefs"][0]["firms"] == 4, "counts must be recomputed, not carried over"


def test_refresh_excludes_the_fixture_from_firm_counts(tmp_path, monkeypatch):
    import json
    docs = tmp_path / "docs" / "data"
    docs.mkdir(parents=True)
    (docs / "briefs.json").write_text(json.dumps({"model": "test", "briefs": [
        {"topic": "T", "firms": 3, "firm_list": ["stale"], "articles": 3, "consensus": "x"},
    ]}))
    monkeypatch.setattr(brief, "DOCS", docs)

    rows = [art("rsmus.com", 0), art("bdo.com", 1),
            art("advisory-digest.vercel.app", 2)]
    assignments = {r["article_url"]: ["T"] for r in rows}

    brief.refresh_counts(rows, assignments)
    out = json.loads((docs / "briefs.json").read_text())
    assert out["briefs"][0]["firms"] == 2
    assert "advisory-digest.vercel.app" not in out["briefs"][0]["firm_list"]
