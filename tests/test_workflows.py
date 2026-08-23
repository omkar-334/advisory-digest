"""The workflow files must parse.

A workflow with a YAML error does not fail loudly: GitHub creates a run with no jobs, and
the Actions tab shows a red X with no log. That happened here — an alerting step with a
nested heredoc broke the file, and the scheduled scrape silently stopped running until
someone thought to parse the file by hand.

Needs pyyaml, which is not otherwise a dependency:
    uv run --with pytest --with pyyaml pytest tests/
"""
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml not installed; run with --with pyyaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def test_there_are_workflows():
    assert WORKFLOWS, "no workflow files found"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_parses(path):
    yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_has_jobs_with_steps(path):
    """A file can parse and still be structurally useless."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = doc.get("jobs") or {}
    assert jobs, f"{path.name} defines no jobs"
    for name, job in jobs.items():
        assert job.get("steps"), f"{path.name}: job '{name}' has no steps"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_scripts_referenced_by_workflows_exist(path):
    """Catch a workflow calling a script that was renamed or deleted."""
    import re
    text = path.read_text(encoding="utf-8")
    for ref in set(re.findall(r"scripts/[A-Za-z0-9_]+\.(?:py|sh)", text)):
        assert (ROOT / ref).exists(), f"{path.name} references missing {ref}"
