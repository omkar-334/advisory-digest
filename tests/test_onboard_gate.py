"""Tests for the source-onboarding eligibility gate.

The gate decides what this project is willing to scrape. Those rules are commitments, not
preferences, so they are pinned here rather than left to whoever edits onboard.py next.

No network and no API key: the gate is a pure function over a classifier verdict.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("onboard", ROOT / "scripts" / "onboard.py")
onboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboard)


def verdict(**over):
    """A clean, eligible listing page. Tests override one field at a time."""
    v = {
        "is_listing_page": True,
        "publisher": "Example Advisory",
        "content_type": "professional articles",
        "requires_login": False,
        "has_paywall": False,
        "is_government": False,
        "personal_data_risk": "none",
        "article_count_estimate": 20,
        "suggested_description": "Extract title, summary, published_date, article_url, tags.",
        "confidence": 0.9,
    }
    v.update(over)
    return v


URL = "https://www.example-advisory.com/insights"


def test_clean_listing_page_is_eligible():
    assert onboard.gate(URL, verdict()) == []


# --- the three absolute rejections -------------------------------------------------

def test_government_site_is_rejected():
    reasons = onboard.gate("https://www.example.gov/news", verdict(is_government=True))
    assert any("government" in r for r in reasons)


@pytest.mark.parametrize("url", [
    "https://eprocure.gov.in/cppp/tenders",
    "https://www.data.gov/catalog",
    "https://service.gov.uk/updates",
    "https://army.mil/news",
])
def test_government_domains_rejected_even_if_classifier_says_otherwise(url):
    """Defence in depth: the host suffix alone is disqualifying.

    The classifier is a language model and can be wrong or talked out of a judgement by
    page content. Rule 7 does not depend on its opinion.
    """
    reasons = onboard.gate(url, verdict(is_government=False))
    assert any("government" in r for r in reasons), url


def test_login_walled_source_is_rejected():
    reasons = onboard.gate(URL, verdict(requires_login=True))
    assert any("login" in r for r in reasons)
    # The refusal must not be phrased as something to work around.
    assert any("will not" in r and "authenticate" in r for r in reasons)


def test_paywalled_source_is_rejected():
    reasons = onboard.gate(URL, verdict(has_paywall=True))
    assert any("paywall" in r for r in reasons)


# --- content-quality rejections -----------------------------------------------------

def test_pages_about_private_individuals_are_rejected():
    reasons = onboard.gate(URL, verdict(personal_data_risk="high"))
    assert any("individuals" in r for r in reasons)


def test_single_article_is_not_a_source():
    reasons = onboard.gate(URL, verdict(is_listing_page=False, content_type="single article"))
    assert any("listing page" in r for r in reasons)


def test_low_personal_data_risk_is_allowed():
    """Author bylines alone must not disqualify a source; they are dropped at extraction."""
    assert onboard.gate(URL, verdict(personal_data_risk="low")) == []


# --- a block is not a rejection -----------------------------------------------------

def test_gate_does_not_consider_http_status():
    """A 403 to a plain request must never disqualify a source.

    crowe.com and marcumllp.com both refuse naive clients and both work through Bright
    Data's unblocking layer. Rejecting on status would have discarded two working sources,
    and would defeat the purpose of routing through an unblocker at all.
    """
    import inspect
    src = inspect.getsource(onboard.gate)
    for token in ("status", "403", "http"):
        assert token not in src.lower(), f"gate() must not branch on {token}"
    assert onboard.gate(URL, verdict()) == []


def test_403_is_reported_as_non_disqualifying():
    """The operator-facing note must say a block is survivable, not fatal."""
    import inspect
    src = inspect.getsource(onboard.fetch)
    assert "not disqualifying" in src


def test_multiple_violations_are_all_reported():
    reasons = onboard.gate("https://data.gov/x",
                           verdict(requires_login=True, has_paywall=True,
                                   is_listing_page=False))
    assert len(reasons) >= 4
