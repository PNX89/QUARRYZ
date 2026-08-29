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


def test_the_repository_does_not_claim_to_detect_a_disappearing_period() -> None:
    """A withdrawn claim, kept as a check so it cannot creep back in.

    There was a dbt test asserting no period ever vanishes between loads, and it could not fail:
    the warehouse and the incoming load are the same table under two prefix bounds, so the
    earlier one's key set is a subset by construction and the anti-join is provably empty. The
    corpus cannot represent the event either, because the capture emits a row when a value
    CHANGES and a dropped period emits nothing.

    Both halves are now said in the model rather than asserted by a test that watches nothing.
    """
    names = {path.stem for path in (DBT / "tests").glob("*.sql")}
    assert "assert_no_period_disappeared" not in names, (
        "the disappearance test is back. It cannot fail while the warehouse and incoming models "
        "are two prefix bounds on one table, so if it is wanted, the models have to change first"
    )
    model = (DBT / "models" / "revisions.sql").read_text(encoding="utf-8")
    assert "DOES NOT CLAIM TO DETECT" in model, (
        "the model no longer says that a disappearing period goes undetected, so a reader is "
        "left to assume the gate covers a case it does not"
    )


def test_the_per_series_split_in_the_transcript_is_the_one_in_the_summary() -> None:
    """FOUR NUMBERS THAT USED TO BE TYPED INTO A HEREDOC.

    The transcript's closing contrast, a series rewritten against a series untouched, carried
    445, 664, 0 and 887 as literal text. Every one of them was correct and none of them was
    computed, so a recapture would have moved the measurement and left the sentence standing.
    That is the defect this repository exists to detect, in its own evidence.
    """
    per_series = summary()["per_series_in_the_declared_window"]
    text = (EVIDENCE / "both-directions.txt").read_text(encoding="utf-8")

    assert len(per_series) >= 2, "one series cannot show a contrast between two"
    for series, entry in per_series.items():
        assert f"{series}  {entry['revised']:>4} of {entry['periods']} periods revised" in text, (
            f"the transcript does not show {series} as {entry['revised']} of {entry['periods']}, "
            f"so the prose and the summary describe different builds"
        )

    revised = [entry["revised"] for entry in per_series.values()]
    assert sum(revised) == summary()["revisions_in_the_declared_window"]
    assert min(revised) == 0, (
        "every series was revised in this window, so the argument for a per-series gate has no "
        "example in the evidence and must not be made in this file"
    )
    assert max(revised) > 0


def test_the_untouched_series_is_untouched_in_the_corpus_and_not_only_in_the_model() -> None:
    """The contrast has to survive being asked of the data instead of the warehouse.

    A per-series count read off the same model the gate builds proves the model consistent with
    itself. The claim is about the publisher: that in these six months one series was rewritten
    and another was not touched at all, which is checkable straight from the committed CSVs.
    """
    window = sorted(entry["released"] for entry in ledger())
    first, last = window[0], window[-1]

    vintages = REPO / "src" / "quarryz" / "data" / "vintages"
    untouched = [
        series
        for series, entry in summary()["per_series_in_the_declared_window"].items()
        if entry["revised"] == 0
    ]
    assert untouched, "no series was left alone, so there is nothing to check"

    for series in untouched:
        path = vintages / f"{series}.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        known = {row["period"] for row in rows if row["released"] < first}
        changed_inside = {row["period"] for row in rows if first <= row["released"] <= last}
        assert not (known & changed_inside), (
            f"{series} is recorded as revising nothing in this window, and its own corpus shows "
            f"{len(known & changed_inside)} already-published periods changing inside it"
        )
