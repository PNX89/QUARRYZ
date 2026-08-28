"""Every committed measurement is produced by a script, and CI runs that script.

A repository arguing that a number without a date is worthless cannot itself carry numbers
nobody re-derives. These tests are the join between three things that are easy to let drift
apart: a directory under `docs/evidence`, the script that writes it, and a CI job that runs the
script and diffs the result.

TWO OF THE THREE ARE THE EASY HALF. Checking that a script exists and that a directory exists
proves nothing about whether they are connected, so what is asserted here is that the workflow
NAMES the script AND diffs the directory the script writes. A job that runs a harness and does
not compare its output is a job that proves the harness does not crash.
"""

from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence"
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def workflow() -> dict[str, object]:
    loaded: dict[str, object] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return loaded


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def evidence_directories() -> list[pathlib.Path]:
    if not EVIDENCE.exists():
        return []
    return sorted(path for path in EVIDENCE.iterdir() if path.is_dir())


def test_every_evidence_directory_has_a_summary_that_is_json() -> None:
    """The transcripts are for a reader and the summary is what CI diffs.

    A harness in a sibling repository wrote a summary that was not JSON at all, twice, and still
    exited zero: once because an unterminated container put the bare word `none` where a number
    belonged, and once because `grep -c .` prints 0 AND exits 1 on empty input, so a fallback
    appended a second zero and the value spanned two lines.
    """
    import json

    directories = evidence_directories()
    assert directories, "there is no committed evidence at all, so this checks nothing"
    for directory in directories:
        summary = directory / "summary.json"
        assert summary.exists(), f"{directory.name} has no summary.json for CI to diff"
        json.loads(summary.read_text(encoding="utf-8"))


def test_a_script_writes_every_evidence_directory() -> None:
    """A committed artefact nobody can regenerate is a claim about the past."""
    scripts = list((REPO / "scripts").glob("*.sh")) + list((REPO / "scripts").glob("*.py"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in scripts)
    for directory in evidence_directories():
        assert directory.name in text, (
            f"nothing under scripts/ mentions docs/evidence/{directory.name}, so that evidence "
            f"cannot be regenerated"
        )


def test_ci_runs_every_harness_and_diffs_what_it_wrote() -> None:
    """The join that matters, and the half a weaker test would miss.

    Running a harness proves it does not crash. Diffing what it wrote is what turns a changed
    outcome into a red build, and the two are separate lines in the workflow, so both are
    asserted for each evidence directory rather than either being taken as the other.
    """
    text = workflow_text()
    for directory in evidence_directories():
        relative = f"docs/evidence/{directory.name}"
        assert f"git diff --exit-code -- {relative}/summary.json" in text, (
            f"CI does not diff {relative}/summary.json, so a changed outcome is not a red build"
        )

    for script in sorted((REPO / "scripts").glob("measure_*.sh")):
        assert f"scripts/{script.name}" in text, f"CI never runs scripts/{script.name}"


def test_every_job_in_the_workflow_is_named() -> None:
    """An unnamed job shows as its key, and the key is not what a reader is told to look for."""
    jobs = workflow()["jobs"]
    assert isinstance(jobs, dict)
    for key, job in jobs.items():
        assert isinstance(job, dict)
        assert job.get("name") or job.get("uses"), f"job {key} has no name"


def test_every_third_party_action_is_pinned_by_commit() -> None:
    """A tag is a pointer its owner can move, and this repository downloads binaries.

    Written with the first workflow rather than after the fact: a sibling shipped twelve floating
    major tags under a generated file claiming every workflow pinned an exact version.
    """
    first_party = "PNX89/"
    uses = re.findall(r"^\s*(?:- )?uses:\s*(\S+)\s*(#.*)?$", workflow_text(), re.MULTILINE)
    assert uses, "the workflow has no `uses:` lines at all"
    for ref, trailing in uses:
        if ref.startswith(first_party):
            continue
        assert re.search(r"@[0-9a-f]{40}$", ref), f"{ref} is pinned by a movable tag"
        assert trailing.strip().startswith("#"), f"{ref} is pinned with no version named beside it"
