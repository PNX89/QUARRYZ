"""The facts the portfolio card states, checked against the repository rather than the file.

`docs/evidence/facts.json` is the one captured artefact CI does NOT compare byte for byte,
because it carries a capture date and a byte comparison of a date fails on the second morning
and teaches everybody to ignore the job. That exemption is only defensible if the numbers
inside it are checked another way, which is what this file is.
"""

from __future__ import annotations

import html
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
CARD = REPO / "site" / "index.html"
DEMO = REPO / "docs" / "evidence" / "demo.txt"


def facts() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FACTS.read_text(encoding="utf-8"))
    return loaded


def card() -> str:
    """The published page, or a skip. A card is written at publication and can be absent."""
    if not CARD.exists():
        pytest.skip("no card is committed yet, so there is nothing published to check")
    return CARD.read_text(encoding="utf-8")


def measured_figures() -> set[int]:
    """Every integer any harness recorded, flattened out of the committed summaries.

    Flattened rather than listed key by key, so a harness that starts recording a new figure
    does not have to be added here before the card is allowed to quote it. What this cannot do
    is notice a figure the page states and no harness produces, which is the direction that
    matters and the one it is used for below.
    """
    found: set[int] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, int):
            found.add(abs(node))
        elif isinstance(node, str):
            if node.lstrip("-").isdigit():
                found.add(abs(int(node)))
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for summary in sorted((REPO / "docs" / "evidence").glob("*/summary.json")):
        walk(json.loads(summary.read_text(encoding="utf-8")))
    walk(facts())

    # The headline move is the DIFFERENCE between two recorded vintages, so no summary carries
    # it as a figure of its own and the page would otherwise be quoting an unmeasured number.
    vintages = json.loads(
        (REPO / "docs" / "evidence" / "snapshots" / "summary.json").read_text(encoding="utf-8")
    )["by_vintage"]
    found.add(abs(int(vintages["as_at_2023_12"]) - int(vintages["as_at_2023_06"])))
    return found


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


def test_the_published_card_carries_no_banned_dash() -> None:
    """The one character that gets a page rejected, checked before it is published.

    That the card was GENERATED from the capture rather than pasted is checked below, against
    the whole transcript. This test kept only the half a comparison cannot cover: the rest of
    the page, which is written from a shared manifest and never diffed against anything.
    """
    published = card()
    # WRITTEN AS ESCAPES, NOT AS THE CHARACTERS. A check for a character cannot be the thing
    # that introduces it, and the linter catches the literal form for exactly that reason.
    for dash in ("\u2014", "\u2013"):
        assert dash not in published, f"the published card contains {dash!r}"


def test_the_transcript_on_the_card_is_the_captured_demo_in_full() -> None:
    """THE SENTENCE ON THE CARD THAT WAS NOT TRUE, and this is what makes it true.

    The card tells its reader, in its own body, that it "is committed to the repository and a
    test fails when it stops matching a live run, so this page cannot quietly drift from the
    code it describes". What existed was a check on the FIRST non-blank line of demo.txt, here
    and again in the Pages publication guard, so 26 of the transcript's 27 lines were unchecked
    in both places. Editing "keeps  2,533" to "keeps  9,999" on the card left the suite green
    and the publication guard accepting, and the page would have deployed.

    Compared after unescaping, because the card is HTML and the capture is not: a transcript
    containing an ampersand would otherwise fail here for being correctly escaped.
    """
    published = card()
    block = re.search(r"<pre[^>]*>(.*?)</pre>", published, re.S)
    assert block, "the card no longer shows the demo transcript at all"
    shown = html.unescape(block.group(1)).strip("\n")
    captured = DEMO.read_text(encoding="utf-8").strip("\n")
    assert shown == captured, (
        "the transcript on the published card is not the committed capture. Re-generate the "
        "card, or if the demo's output has moved, re-run scripts/capture_evidence.py first"
    )


def test_the_facts_strip_on_the_card_states_the_captured_facts() -> None:
    """Three cells, each a second copy of a figure, and nothing reconciled any of them.

    The strip is the most prominent thing on the page after the headline, and every cell was
    hand-carried from facts.json by the generator. Changing the test count to 4242 published a
    card advertising a suite four times the size of the one that runs.

    Asserted as the whole strip rather than cell by cell, so a cell that disappears is a failure
    too: a card that has quietly stopped stating its test total is not a card that passed.
    """
    published = card()
    strip = re.search(r'<dl class="facts">(.*?)</dl>', published, re.S)
    assert strip, "the card no longer carries a facts strip"
    stated = dict(re.findall(r"<dt>([^<]+)</dt><dd>([^<]*)</dd>", strip.group(1)))
    assert stated == {
        "Tests": str(facts()["tests"]),
        "Python": facts()["python"],
        "Release": facts()["release"],
    }, f"the card states {stated} and docs/evidence/facts.json records {facts()}"


def test_no_figure_the_card_quotes_is_one_nothing_measured() -> None:
    """The claim paragraph, which is prose from a shared manifest and quotes two measurements.

    THE FIGURE IN THE SENTENCE THAT CARRIES IT, and not a search of the page for the figure: a
    page this long contains any small number somewhere, so finding one proves nothing. What is
    read is the claim paragraph, and every number in it has to be one a harness produced.
    Rewriting "destroys 71 of them" to "destroys 999 of them" published unchallenged.

    Numbers of two digits and up, because a one-digit figure in a sentence is usually a count of
    something on the page rather than a measurement, and no allowlist can tell a wrong 7 from a
    right one.
    """
    published = card()
    claim = re.search(r'<p class="claim">(.*?)</p>', published, re.S)
    assert claim, "the card no longer makes a claim, which is the only thing a card is for"
    quoted = {
        int(token.replace(",", ""))
        for token in re.findall(r"\b\d{1,3}(?:,\d{3})*\b", claim.group(1))
        if len(token.replace(",", "")) > 1
    }
    assert quoted, "the claim paragraph quotes no measurement at all"
    invented = sorted(quoted - measured_figures())
    assert invented == [], (
        f"the card claims {invented}, and nothing under docs/evidence produces those figures. "
        f"Either a measurement moved and the card was left behind, or the number was typed"
    )


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
