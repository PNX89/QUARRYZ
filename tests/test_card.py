"""The facts the portfolio card states, checked against the repository rather than the file.

`docs/evidence/facts.json` is the one captured artefact CI does NOT compare byte for byte,
because it carries a capture date and a byte comparison of a date fails on the second morning
and teaches everybody to ignore the job. That exemption is only defensible if the numbers
inside it are checked another way, which is what this file is.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tomllib
from typing import Any

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
FACTS = REPO / "docs" / "evidence" / "facts.json"


def facts() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FACTS.read_text(encoding="utf-8"))
    return loaded


def test_the_stated_test_total_is_the_one_this_suite_collects() -> None:
    """The number most likely to be stale, because it moves on every commit that adds a test."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=True,
    )
    collected = sum(
        int(count) for _, count in re.findall(r"^(tests/\S+): (\d+)$", result.stdout, re.MULTILINE)
    )
    assert collected > 0, "nothing was collected, so this test is comparing against zero"
    assert facts()["tests"] == collected, (
        f"the card states {facts()['tests']} tests and the suite collects {collected}. Re-run "
        f"scripts/capture_evidence.py"
    )


def test_the_stated_python_range_is_the_one_ci_runs() -> None:
    """A range read from `requires-python` would state a floor nothing executes."""
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    versions = re.findall(r'"(\d+\.\d+)"', workflow)
    assert versions, "the CI file names no Python versions"
    expected = f"{min(versions, key=float)} to {max(versions, key=float)}"
    assert facts()["python"] == expected, (
        f"the card states {facts()['python']} and CI runs {expected}"
    )


def test_the_stated_release_matches_the_package_version() -> None:
    """A card naming a release nobody can download is worse than a card naming none."""
    version = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    stated = facts()["release"]
    assert stated.startswith(f"v{version}"), (
        f"the card states the release as {stated} and pyproject says {version}"
    )


def test_the_capture_date_is_not_in_the_future() -> None:
    """The one field that cannot be recomputed, so it is bounded instead of matched.

    Checking it against today would make this test fail every day after the capture, which is
    the same trap as diffing the file. What can honestly be said is that a capture cannot have
    happened tomorrow, and that a date in the future means the field was typed.
    """
    import datetime

    captured = datetime.date.fromisoformat(facts()["captured"])
    assert captured <= datetime.date.today(), (
        f"the card says it was captured on {captured}, which has not happened yet"
    )


def test_the_card_is_not_committed_before_the_repository_ships() -> None:
    """A card is written at publication, and one that arrives early advertises nothing real.

    If `site/index.html` exists, it must be the generated card rather than a placeholder, and
    the demo output it shows has to be the committed capture rather than a paste.
    """
    card = REPO / "site" / "index.html"
    if not card.exists():
        return
    html = card.read_text(encoding="utf-8")
    demo = (REPO / "docs" / "evidence" / "demo.txt").read_text(encoding="utf-8")
    first = next(line for line in demo.splitlines() if line.strip())
    assert first in html, (
        "the published card does not contain the first line of the captured demo output, so it "
        "was not generated from it"
    )
    # WRITTEN AS ESCAPES, NOT AS THE CHARACTERS. A check for a character cannot be the thing
    # that introduces it, and the linter catches the literal form for exactly that reason.
    for dash in ("\u2014", "\u2013"):
        assert dash not in html, f"the published card contains {dash!r}"


def test_the_python_range_is_the_gating_matrix_and_orders_as_versions(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two latent defects in the function that publishes this number, neither of them visible.

    The range on the card is correct today. It was produced by a function that matched every
    quoted `x.y` anywhere in the workflow, so a quoted action version or a timeout would have
    landed on a published page, and that ordered with `float`, so `float("3.9") > float("3.13")`
    and a 3.9 leg would have published a range running backwards.

    A correct output from a broken mechanism is the thing this whole portfolio argues against, so
    the mechanism is tested rather than the output.
    """
    import json as _json
    import sys

    import yaml

    sys.path.insert(0, str(REPO / "scripts"))
    import capture_evidence

    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    gating: set[str] = set()
    for job in (workflow.get("jobs") or {}).values():
        if job.get("continue-on-error"):
            continue
        declared = (job.get("with") or {}).get("python-versions")
        if declared is None:
            continue
        gating.update(
            str(v) for v in (_json.loads(declared) if isinstance(declared, str) else declared)
        )

    assert gating, "no job gates on a Python version, so the published range verifies nothing"
    order = sorted(gating, key=lambda v: tuple(int(p) for p in v.split(".")))
    expected = f"{order[0]} to {order[-1]}"

    assert capture_evidence.python_range() == expected
    facts = _json.loads((REPO / "docs" / "evidence" / "facts.json").read_text("utf-8"))
    assert facts["python"] == expected, (
        f"the card says {facts['python']} and CI gates on {expected}"
    )

    # THE ORDERING RULE, DRIVEN THROUGH THE REAL FUNCTION rather than restated beside it.
    #
    # This matters because of how the defect hides. No matrix in this repository contains a 3.9,
    # so float ordering and version ordering agree on every version actually present, and
    # swapping the production line back to `key=float` changes no output and fails nothing. A
    # test that only asserted the rule as arithmetic would pin a fact and let the code revert.
    #
    # So the function is pointed at a workflow that DOES contain a 3.9, by moving its ROOT, and
    # asked what it returns. Under `key=float` that is "3.11 to 3.9", a range running backwards
    # on a published page.
    fake = tmp_path / ".github" / "workflows"
    fake.mkdir(parents=True)
    (fake / "ci.yml").write_text(
        'jobs:\n  checks:\n    with:\n      python-versions: \'["3.11", "3.9", "3.13"]\'\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(capture_evidence, "ROOT", tmp_path)
    assert capture_evidence.python_range() == "3.9 to 3.13", (
        "the version range is not ordered as versions. float('3.9') is greater than "
        "float('3.13'), so this publishes a range running backwards the day a 3.9 leg exists"
    )
