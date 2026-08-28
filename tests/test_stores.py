"""The storage table, joined to the measurement rather than trusted.

THE JOIN IS THE POINT OF THIS FILE. Every entry in `STORES` names the keys in
`docs/evidence/collapse/summary.json` that back it, and those keys are read and compared here.
A sibling repository kept a table of detector claims that nothing checked, and when it was
finally joined to its own measurements three of six entries were wrong, every one of them in the
direction that flattered the repository. The join is what stops that, and it has to be TOTAL:
an entry that names no evidence is an opinion with a dataclass around it.

`as_of` is tested against the real corpus rather than a fixture, because the question it answers
is the one the whole repository exists for and a fixture would be a question I wrote to be easy.
"""

from __future__ import annotations

import csv
import json
import pathlib
from typing import Any

import pytest

from quarryz.stores import CLOCKS, STORES, Store, as_of

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "collapse" / "summary.json"
VINTAGES = REPO / "src" / "quarryz" / "data" / "vintages"


def summary() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    return loaded


def measurement(dotted: str) -> Any:
    """One value out of the evidence, addressed the way the store entry addresses it."""
    node: Any = summary()
    for step in dotted.split("."):
        node = node[step]
    return node


def triples(cdid: str) -> list[tuple[str, str, str]]:
    with (VINTAGES / f"{cdid}.csv").open(encoding="utf-8", newline="") as handle:
        return [(row["period"], row["value"], row["released"]) for row in csv.DictReader(handle)]


@pytest.mark.parametrize("store", STORES, ids=lambda s: s.name)
def test_every_store_names_evidence_that_exists(store: Store) -> None:
    """An entry naming no measurement, or a key that is not there, is an opinion."""
    assert store.evidence, f"{store.name} names no evidence at all"
    for key in store.evidence:
        measurement(key)  # raises if the key is not in the summary


def test_the_obvious_design_loses_a_vintage_and_the_evidence_says_so() -> None:
    """The first entry is the exhibit, so its numbers are asserted rather than described."""
    before = measurement("naive_key.rows_before_merge")
    after = measurement("naive_key.rows_after_optimize")
    assert before == 2 and after == 1, (
        f"the naive table read {before} rows then {after}, so the entry claiming it loses a "
        f"vintage is no longer supported by the measurement"
    )


def test_the_batch_load_never_wrote_the_earlier_vintage_at_all() -> None:
    """The worse half, and the one a merge-scheduling explanation does not cover."""
    assert measurement("one_insert.rows") == 1
    assert measurement("one_insert.active_parts") == 1, (
        "more than one part exists, so a merge could have been the explanation and this entry "
        "is claiming something the measurement does not show"
    )


def test_the_vintage_in_the_key_keeps_both_and_still_answers_the_question() -> None:
    """Keeping history is only interesting if the as-of answer survives with it."""
    assert measurement("vintage_in_key.rows") == 2
    assert measurement("vintage_in_key.as_of_2020") != measurement("vintage_in_key.as_of_2021"), (
        "the two as-of answers are equal, so the fixture holds no revision and the comparison "
        "between the two designs shows nothing"
    )


def test_no_store_claims_to_lose_nothing_while_naming_what_decides_the_loss() -> None:
    """A contradiction inside one entry, which is how a table of prose goes quietly wrong."""
    for store in STORES:
        loses_nothing = store.loss_decided_by.startswith("nothing")
        assert loses_nothing == ("never" in store.keeps or "every version" in store.keeps), (
            f"{store.name} says loss is decided by {store.loss_decided_by!r} and that it keeps "
            f"{store.keeps!r}, and those two do not agree"
        )


def test_the_three_clocks_are_named_and_each_says_what_it_is_confused_with() -> None:
    """The repository's thesis, kept as data so it cannot drift out of the prose."""
    names = [clock.name for clock in CLOCKS]
    assert names == ["valid time", "transaction time", "snapshot time"]
    snapshot = CLOCKS[2]
    assert "transaction time" in snapshot.confused_with, (
        "the snapshot clock does not say what it is mistaken for, which is the whole thesis"
    )
    for clock in CLOCKS:
        assert len(clock.confused_with) > 40, clock.name


def test_as_of_answers_the_headline_revision_from_the_real_corpus() -> None:
    """The question the repository exists to answer, asked of the committed data.

    Asked at three moments about one period: before the revision, after it, and today. A
    warehouse that gives the same answer to all three has thrown the history away.
    """
    rows = triples("IKBJ")
    early = as_of(rows, "2021", "2023-06")
    late = as_of(rows, "2021", "2023-12")
    now = as_of(rows, "2021", "2026")

    assert early is not None and late is not None and now is not None
    assert early[0] == "-28039", early
    assert late[0] == "-3518", late
    assert early[0] != late[0], "the revision is invisible to as_of, which is the one job it has"
    assert late[1] == "2023-10-11"


def test_as_of_says_nothing_rather_than_zero_before_the_publisher_spoke() -> None:
    """A period nobody had published yet is not a zero and not a missing key."""
    rows = triples("IKBJ")
    assert as_of(rows, "2021", "2015") is None


def test_as_of_compares_a_year_correctly_and_not_by_string_length() -> None:
    """The bug this function is written to avoid, asserted rather than commented.

    A caller asking as at "2023" means the end of 2023. Comparing that against "2023-10-11" with
    a plain `<=` puts the release AFTER the question, because "2023-10-11" > "2023" lexically,
    so the October revision would be invisible to anyone asking about the year.
    """
    rows = triples("IKBJ")
    by_year = as_of(rows, "2021", "2023")
    by_day = as_of(rows, "2021", "2023-12-31")
    assert by_year is not None and by_day is not None
    assert by_year[0] == by_day[0] == "-3518", (
        f"asking as at a year gave {by_year} and asking as at that year's last day gave "
        f"{by_day}, so the comparison is being done on string length rather than on the date"
    )


def test_a_withdrawal_comes_back_as_a_withdrawal_and_not_as_a_number() -> None:
    """The publisher emptied a value. as_of must say so rather than skipping to the last number."""
    rows = triples("IKBJ")
    withdrawn = [(period, released) for period, value, released in rows if value == "WITHDRAWN"]
    assert withdrawn, "no withdrawal in the corpus, so this cannot be tested here"
    period, released = withdrawn[0]
    answer = as_of(rows, period, released)
    assert answer is not None and answer[0] == "WITHDRAWN", (
        f"as at {released} the publisher had withdrawn {period}, and as_of answered {answer}"
    )
