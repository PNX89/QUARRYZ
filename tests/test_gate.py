"""The build that fails when a publisher rewrites history.

The offline half reads what `scripts/measure_gate.sh` recorded, so it checks something real on a
machine with no dbt and no DuckDB installed. The build itself is its own CI job.

THE CLAIM THIS FILE EXISTS TO PROTECT is that the gate has been SEEN TO FAIL. A gate nobody has
watched fail is a gate nobody has tested, and the commonest way for one to be useless is for it
to be satisfiable by doing nothing. So the harness runs the build twice, once with the ledger
emptied and once with the committed one, and both outcomes are asserted here.
"""

from __future__ import annotations

import csv
import json
import pathlib
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "gate"
LEDGER = REPO / "src" / "quarryz" / "data" / "declared_revisions.csv"
DBT = REPO / "dbt"


def summary() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    return loaded


def ledger() -> list[dict[str, str]]:
    with LEDGER.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_gate_has_been_seen_to_fail() -> None:
    """The claim the repository is named for, and the one worth doubting.

    With the ledger emptied the build must fail, and the number of release groups it names is
    recorded rather than described, because "it failed" is satisfied by a syntax error.
    """
    undeclared = summary()["undeclared_release_groups_when_ledger_emptied"]
    assert undeclared > 0, (
        "emptying the ledger produced no undeclared revisions, so the gate passes whatever the "
        "publisher does and this repository has nothing to say"
    )
    text = (EVIDENCE / "both-directions.txt").read_text(encoding="utf-8")
    assert "with the ledger emptied" in text
    assert f"Got {undeclared} results" in text, (
        "the transcript does not show the failure it claims, so a reader has to take it on trust"
    )


def test_the_gate_has_also_been_seen_to_pass() -> None:
    """A gate that cannot be satisfied is a gate that gets disabled on the second Monday."""
    text = (EVIDENCE / "both-directions.txt").read_text(encoding="utf-8")
    assert "Completed successfully" in text


def test_every_declared_release_is_one_the_data_actually_contains() -> None:
    """A ledger row for a release that never happened is a rubber stamp with nothing under it.

    This is the half a gate usually lacks: declaring is cheap, so nothing stops somebody adding
    a row to make a build green. Each declaration is checked against the corpus.
    """
    from collections import defaultdict

    vintages = REPO / "src" / "quarryz" / "data" / "vintages"
    releases: dict[str, set[str]] = defaultdict(set)
    for path in sorted(vintages.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                releases[path.stem].add(row["released"])

    for entry in ledger():
        assert entry["released"] in releases[entry["series"]], (
            f"the ledger declares {entry['series']} {entry['released']}, and that series has no "
            f"release on that date"
        )
        assert int(entry["periods_expected"]) > 0
        assert entry["note"].strip(), (
            f"{entry['series']} {entry['released']} is declared with no note, so nobody can tell "
            f"whether it was reviewed or waved through"
        )


def test_the_ledger_declares_exactly_what_the_window_revised() -> None:
    """The counts have to add up, or the ledger is describing a different load."""
    declared_total = sum(int(entry["periods_expected"]) for entry in ledger())
    assert declared_total == summary()["revisions_in_the_declared_window"], (
        f"the ledger accounts for {declared_total} revised periods and the window contains "
        f"{summary()['revisions_in_the_declared_window']}"
    )
    assert len(ledger()) == summary()["releases_declared_in_the_ledger"]


def test_the_count_is_part_of_the_declaration_and_not_only_the_release() -> None:
    """Otherwise declaring a release is a blanket permission for whatever it does next time."""
    model = (DBT / "models" / "undeclared_revisions.sql").read_text(encoding="utf-8")
    assert "periods_expected != counted.periods" in model, (
        "the gate matches on the release alone, so accepting one release accepts any number of "
        "changes it makes on any later run"
    )


def test_a_new_period_is_not_treated_as_a_revision() -> None:
    """The distinction that decides whether anybody leaves the gate switched on.

    Every load adds periods, because time passes. A gate that fires on those fires on every load
    and is gone within a week, so `revisions` joins on periods the warehouse ALREADY holds.
    """
    model = (DBT / "models" / "revisions.sql").read_text(encoding="utf-8")
    assert "inner join" in model.lower(), (
        "revisions does not inner join the warehouse, so periods appearing for the first time "
        "would be reported as revisions"
    )


def test_all_three_kinds_of_change_are_exercised_by_a_real_window() -> None:
    """A branch nothing reaches is a branch nobody has tested.

    The declared window holds 1,058 revisions and every one is a plain change, so the withdrawn
    and restored branches would be dead code if they were only measured there. Two older windows
    reach them, and the harness refuses to write a summary in which they do not.
    """
    older = summary()["kinds_in_the_older_windows"]
    assert older["withdrawal_window"].get("withdrawn", 0) > 0
    assert older["restoration_window"].get("restored", 0) > 0


def test_a_period_disappearing_is_a_separate_test_rather_than_an_assumption() -> None:
    """It has never happened here, which is exactly why the silence must not be read as cover."""
    tests = sorted((DBT / "tests").glob("*.sql"))
    names = {path.stem for path in tests}
    assert "assert_no_period_disappeared" in names, (
        "nothing asserts that a period never vanishes between loads, which is a third event "
        "that neither the revision model nor the new-period case would notice"
    )
