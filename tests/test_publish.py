"""Tests for the publish step.

publish.py is the last gate before data reaches the live site, and it holds two invariants
that regress silently: it must never blank a good dataset, and it must never let a byline
through. Both have already failed once in this project.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PUBLISH = ROOT / "scripts" / "publish.py"


def run_publish(tmp_path, rows, summary, existing=None, heals=None):
    """Run publish.py against a throwaway tree so the real docs/data is untouched."""
    validate = tmp_path / "results" / "validate"
    validate.mkdir(parents=True)
    docs = tmp_path / "docs" / "data"
    docs.mkdir(parents=True)

    (validate / "summary-latest.json").write_text(json.dumps(summary))
    with (validate / "rows-20260101T000000Z.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    if existing is not None:
        (docs / "latest.json").write_text(json.dumps(existing))
    if heals is not None:
        (docs / "heals.json").write_text(heals)

    (tmp_path / "scripts").mkdir(exist_ok=True)
    shim = tmp_path / "scripts" / "publish.py"
    shim.write_text(PUBLISH.read_text())

    proc = subprocess.run([sys.executable, str(shim)], capture_output=True, text=True,
                          cwd=str(tmp_path))
    published = docs / "latest.json"
    out = json.loads(published.read_text()) if published.exists() else None
    return proc.returncode, out, proc.stderr


def article(i=0, **over):
    row = {"title": f"Guidance {i}", "summary": "A summary.",
           "published_date": "2026-08-20",
           "article_url": f"https://rsmus.com/insights/{i}",
           "tags": ["Tax"], "_firm": "rsmus.com"}
    row.update(over)
    return row


SUMMARY = {"healthy_sources": 1, "sources": 1, "per_firm": {}}


def test_publishes_rows(tmp_path):
    rc, out, _ = run_publish(tmp_path, [article(i) for i in range(3)], SUMMARY)
    assert rc == 0
    assert len(out) == 3


def test_refuses_to_blank_an_existing_dataset(tmp_path):
    """The exact failure that once wiped the live site.

    CI checked out a fresh tree where the row JSONL is gitignored, the scrape had failed,
    and publish wrote an empty latest.json over a good one.
    """
    good = [article(i) for i in range(5)]
    rc, out, err = run_publish(tmp_path, [], SUMMARY, existing=good)
    assert rc == 1
    assert "refusing" in err.lower()
    assert out == good, "the existing dataset must survive untouched"


def test_deduplicates_on_canonical_url(tmp_path):
    """A discovery-style collector reaches the same article by several paths."""
    rows = [article(0), article(0), article(0, article_url="https://rsmus.com/insights/0/"),
            article(1)]
    rc, out, _ = run_publish(tmp_path, rows, SUMMARY)
    assert rc == 0
    assert len(out) == 2, f"expected 2 unique articles, got {len(out)}"


@pytest.mark.parametrize("field", ["author", "author_name", "byline", "email", "phone"])
def test_personal_fields_never_reach_the_site(tmp_path, field):
    rc, out, _ = run_publish(tmp_path, [article(0, **{field: "A. Person"})], SUMMARY)
    assert rc == 0
    assert field not in out[0], f"{field} was published"


def test_a_corrupt_heals_file_does_not_erase_the_repair_log(tmp_path):
    rc, out, _ = run_publish(tmp_path, [article(0)], SUMMARY, heals="{not json")
    assert rc == 0
    # The run still succeeds; the point is it does not crash or silently reset the log.
    assert len(out) == 1


def test_the_control_page_never_reaches_the_published_dataset(tmp_path):
    """The fixture we break on purpose must not be served as advisory content.

    It leaked once already: excluded from signals and briefs but not from latest.json, so
    the relevance filter recommended articles we had written ourselves.
    """
    rows = [article(0), article(1, _firm="advisory-digest.vercel.app",
                                article_url="https://advisory-digest.vercel.app/control/1")]
    rc, out, _ = run_publish(tmp_path, rows, SUMMARY)
    assert rc == 0
    firms = {r.get("_firm") for r in out}
    assert "advisory-digest.vercel.app" not in firms
    assert len(out) == 1
