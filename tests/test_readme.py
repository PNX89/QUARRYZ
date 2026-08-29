"""Every checkable claim on the front page, checked.

The README is the only document most readers open, so every number on it is computed here from
the evidence the harnesses wrote, and every path it names is opened. The four kinds of claim in
the shared contract, implemented for this repository:

    NUMBER     a figure on the page against the measurement that produced it
    COMMAND    a command the page tells a reader to run against what CI actually runs
    OUTPUT     a block quoted on the page against the transcript it was taken from
    REFERENCE  every link and path against what exists

WRITTEN BEFORE THE README WAS, which is the only ordering that works. A test written afterwards
is a transcription of whatever the page happens to say, and it passes on the day it is written
whatever that is.
"""

from __future__ import annotations

import csv
import json
import pathlib
import re
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text(encoding="utf-8")
EVIDENCE = REPO / "docs" / "evidence"
VINTAGES = REPO / "src" / "quarryz" / "data" / "vintages"


def evidence(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (EVIDENCE / name / "summary.json").read_text(encoding="utf-8")
    )
    return loaded


def source() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((VINTAGES / "SOURCE.json").read_text(encoding="utf-8"))
    return loaded


def test_the_numbers_on_the_page_are_the_measured_ones() -> None:
    """NUMBER, as a table of claim against source rather than as separate tests.

    The failure mode is somebody editing one figure and not its neighbours, and a table makes
    the omission visible in one place.
    """
    collapse = evidence("collapse")["whole_corpus"]
    gate = evidence("gate")
    snapshots = evidence("snapshots")
    agreement = evidence("agreement")["moments"]
    series = source()["series"]

    claims = {
        "the corpus row count": f"{collapse['rows']:,}",
        "what a date key destroys": f"{collapse['destroyed_by_a_date_key']}",
        "what a date key keeps": f"{collapse['kept_by_a_date_key']:,}",
        "versions walked": f"{sum(entry['versions'] for entry in series)}",
        "series": f"{len(series)}",
        "undeclared groups when the ledger is emptied": str(
            gate["undeclared_release_groups_when_ledger_emptied"]
        ),
        "revisions in the declared window": f"{gate['revisions_in_the_declared_window']:,}",
        "loads": f"{snapshots['loads']}",
        "snapshots": f"{snapshots['snapshots']}",
        "periods compared by three engines": f"{agreement['2023-08']['periods_compared']}",
        "periods the tie decided": str(
            len(agreement["2016-01"]["periods_where_the_tie_decided_the_answer"])
        ),
    }
    missing = {name: value for name, value in claims.items() if value not in README}
    assert missing == {}, f"the README no longer states these measured figures: {missing}"


def test_the_headline_revision_on_the_page_is_the_arithmetic_of_the_corpus() -> None:
    """NUMBER, and the one a reader is most likely to quote back.

    Both endpoints and the difference are asserted, because a page carrying two numbers and
    their difference is a page with three chances to be wrong and one of them is silent.
    """
    snapshots = evidence("snapshots")
    before = int(snapshots["by_vintage"]["as_at_2023_06"])
    after = int(snapshots["by_vintage"]["as_at_2023_12"])

    assert f"{before:,}" in README, f"the README no longer states {before:,}"
    assert f"{after:,}" in README, f"the README no longer states {after:,}"
    assert f"{abs(after - before):,}" in README, (
        f"the README states two values whose difference is {abs(after - before):,} and does not "
        f"state that difference anywhere"
    )


def test_the_untouched_series_is_named_with_its_measured_counts() -> None:
    """NUMBER. The contrast the gate design rests on, quoted with the numbers behind it."""
    per_series = evidence("gate")["per_series_in_the_declared_window"]
    untouched = [name for name, entry in per_series.items() if entry["revised"] == 0]
    assert untouched, "no series was left alone in the declared window"
    for name in untouched:
        assert name in README, f"the README does not name {name}, the series the window spared"
        assert f"{per_series[name]['periods']}" in README


def test_every_command_the_page_offers_is_one_ci_runs() -> None:
    """COMMAND. A README that tells a reader to run something CI does not is a README with a
    step that has not worked for a month and nobody noticed."""
    import yaml

    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    executed = "\n".join(
        line
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
        for line in step["run"].splitlines()
        if not line.strip().startswith("#")
    )

    # THE THREE THAT ARE NOT IN THIS FILE, and naming them is the honest way to skip them.
    # Lint, types and the offline suite run in the shared reusable workflow this CI file calls,
    # so their command lines live in another repository and cannot be matched here. What CAN be
    # checked is that the delegation is real, so it is.
    shared = "PNX89/.github/.github/workflows/checks.yml"
    assert shared in (REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"), (
        "CI no longer calls the shared checks workflow, so the three commands skipped below are "
        "run by nothing and this test is waving them through"
    )
    delegated = ("uv run pytest", "uv run ruff", "uv run mypy")

    offered = re.findall(r"^\s*(?:\$ )?(scripts/\S+|uv run [^\n]+)$", README, re.MULTILINE)
    assert offered, "the README offers no command at all"
    for command in offered:
        command = command.strip()
        if command.startswith(delegated):
            continue
        assert command in executed, f"the README offers `{command}` and CI never runs it"


def test_every_block_quoted_from_a_transcript_is_in_that_transcript() -> None:
    """OUTPUT. Every line of every quoted block, against the file it names.

    The marker is an HTML comment naming the source, so it does not render, and the check is
    per line rather than per block: a page that pastes six lines of output and changes one of
    them is exactly as wrong as one that invents all six, and much harder to notice.
    """
    blocks = re.findall(r"<!-- quoted from (\S+) -->\n```text\n(.*?)```", README, re.S)
    assert blocks, "no block on the page declares where it was quoted from"
    for path, body in blocks:
        source_file = REPO / path
        assert source_file.exists(), f"the page quotes {path}, which does not exist"
        lines = {line.strip() for line in source_file.read_text("utf-8").splitlines()}
        for line in body.splitlines():
            if line.strip():
                assert line.strip() in lines, (
                    f"the page quotes {line.strip()!r} as coming from {path}, and that file "
                    f"does not contain the line"
                )


def test_every_path_and_link_on_the_page_exists() -> None:
    """REFERENCE. Including the ones inside inline code, which is how paths are usually written."""
    targets = set(re.findall(r"\]\((?!https?:)([^)#]+)", README))
    targets |= {
        found
        for found in re.findall(r"`([a-zA-Z0-9_./-]+)`", README)
        if "/" in found and not found.startswith(("http", "-"))
    }
    missing = sorted(target for target in targets if not (REPO / target.strip()).exists())
    assert missing == [], f"the README points at paths that do not exist: {missing}"


def test_the_page_does_not_claim_to_answer_the_question_a_sibling_answers() -> None:
    """The boundary this repository has to hold, asserted rather than remembered.

    QUARRYZ is a warehouse and a revision detector. It is not a second point-in-time answering
    service, and a README drifting into that language is a README describing a different
    repository. The phrases banned here are the ones that describe answering a user's question
    rather than storing and gating a publisher's revisions.
    """
    forbidden = ("refuse", "refusal", "agent", "oracle", "asks the model", "answers the user")
    found = [phrase for phrase in forbidden if phrase in README.lower()]
    assert found == [], (
        f"the README uses {found}, which is the language of the sibling that answers questions "
        f"rather than the one that stores revisions"
    )


def test_the_corpus_is_described_by_its_actual_size_on_disk() -> None:
    """NUMBER. A figure that drifts silently every time the capture is re-run."""
    size = sum(path.stat().st_size for path in VINTAGES.glob("*.csv"))
    assert f"{round(size / 1024)} kB" in README, (
        f"the committed corpus is {round(size / 1024)} kB and the README does not say so"
    )


def test_the_licence_the_page_names_is_the_one_the_capture_recorded() -> None:
    """REFERENCE, and the one with a legal consequence rather than a cosmetic one."""
    assert source()["licence"] in README, "the README does not name the publisher's licence"
    assert "Open Government Licence" in README
    with (VINTAGES / "IKBJ.csv").open(encoding="utf-8", newline="") as handle:
        assert csv.DictReader(handle).fieldnames == ["period", "value", "released", "version"]


def test_no_large_number_on_the_page_is_one_nothing_measured() -> None:
    """THE HALF `in README` CANNOT DO, and a mutation proved it was missing.

    Every other check here asks whether a measured figure appears somewhere on the page. That
    passes while a SECOND, stale copy of the same figure sits three paragraphs up: editing
    "23,943 published values" in a heading to 23,940 left the whole suite green, because the
    correct number still appeared further down.

    So this works the other way round. Every comma-grouped number on the page has to be one
    something in this repository actually produced. It only covers figures of four digits and
    up, which is where staleness hides: a page saying 5 loads instead of 3 is caught by the
    table above, and no allowlist can tell a wrong 7 from a right one.
    """
    collapse = evidence("collapse")
    gate = evidence("gate")
    snapshots = evidence("snapshots")
    agreement = evidence("agreement")["moments"]
    series = source()["series"]

    june = int(snapshots["by_vintage"]["as_at_2023_06"])
    december = int(snapshots["by_vintage"]["as_at_2023_12"])

    measured: set[int] = {
        collapse["whole_corpus"]["rows"],
        collapse["whole_corpus"]["kept_by_a_date_key"],
        collapse["whole_corpus"]["destroyed_by_a_date_key"],
        gate["revisions_in_the_declared_window"],
        gate["undeclared_release_groups_when_ledger_emptied"],
        gate["releases_declared_in_the_ledger"],
        snapshots["loads"],
        snapshots["snapshots"],
        snapshots["rows_june"],
        snapshots["rows_december"],
        snapshots["objects_in_s3"],
        abs(june),
        abs(december),
        abs(december - june),
        len(series),
        sum(entry["versions"] for entry in series),
        sum(entry["changes"] for entry in series),
        round(sum(path.stat().st_size for path in VINTAGES.glob("*.csv")) / 1024),
    }
    for moment in agreement.values():
        measured.add(moment["periods_compared"])
        measured.add(len(moment["periods_where_the_tie_decided_the_answer"]))
    for entry in gate["per_series_in_the_declared_window"].values():
        measured.update({entry["periods"], entry["revised"]})
    for entry in series:
        measured.update({entry["versions"], entry["changes"], entry["distinct_release_dates"]})

    written = {
        int(token.replace(",", "")) for token in re.findall(r"\b\d{1,3}(?:,\d{3})+\b", README)
    }
    invented = sorted(written - measured)
    assert invented == [], (
        f"the page states {invented}, and nothing under docs/evidence or in SOURCE.json "
        f"produces those figures. Either a measurement moved and one copy was left behind, or "
        f"the number was written by hand"
    )
