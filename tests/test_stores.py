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


def test_the_pair_key_keeps_both_and_still_answers_the_question() -> None:
    """Keeping history is only interesting if the as-of answer survives with it.

    Measured on two versions the publisher really did release on the same day, so the as-of
    projection has to break the tie as well as the storage: argMax over the DATE alone has no
    defined answer here, which is the same defect one level up.
    """
    assert measurement("vintage_and_version.rows") == 2
    assert measurement("vintage_and_version.as_of_v3") != measurement(
        "vintage_and_version.as_of_v4"
    ), (
        "the two as-of answers are equal, so the fixture holds no same-day pair and the "
        "comparison between the two designs shows nothing"
    )


def test_an_entry_claiming_to_lose_nothing_is_checked_against_the_corpus() -> None:
    """The guard that replaced one which compared PROSE TO PROSE and therefore could not fail.

    The old version asserted that `loss_decided_by` starting with "nothing" agreed with the
    wording of `keeps`. Both are strings in the same file written by the same person in the same
    minute, so they agreed, and the entry they were guarding was false: it offered
    `ORDER BY (series, period, vintage)` as the design that loses nothing, and a date-only key
    destroys 71 of the 23,943 rows in the committed corpus.

    What is checked now is the corpus. An entry claiming to lose nothing must name a measurement
    showing the whole corpus survived it.
    """
    corpus = measurement("whole_corpus.rows")
    for store in STORES:
        if store.loses_history:
            continue
        survived = [
            measurement(key) for key in store.evidence if key.startswith("whole_corpus.kept")
        ]
        assert survived, (
            f"{store.name} claims to lose nothing and names no whole-corpus measurement, so the "
            f"claim rests on a two-row fixture. That is exactly how the previous version of this "
            f"table came to recommend a design that destroys 71 published values"
        )
        assert all(kept == corpus for kept in survived), (
            f"{store.name} claims to lose nothing and its own measurement says {survived} rows "
            f"survived out of {corpus}"
        )


def test_an_entry_claiming_to_lose_history_can_show_the_loss() -> None:
    """The other direction, and a mutation walked straight through its absence.

    Marking the honest design as losing history passed every test here, because the guard only
    read entries claiming to lose NOTHING. Understating a design's safety is a smaller sin than
    overstating it and it is still a false claim, and a table where half the rows are unchecked
    is a table that will drift on the unchecked half.

    So an entry claiming loss must name a measurement that SHOWS one: either a row count that
    fell, or a corpus figure short of the whole.
    """
    corpus = measurement("whole_corpus.rows")
    for store in STORES:
        if not store.loses_history:
            continue
        shows_loss = False
        for key in store.evidence:
            value = measurement(key)
            if key.startswith("whole_corpus.destroyed") and value > 0:
                shows_loss = True
            if key.startswith("whole_corpus.kept") and value < corpus:
                shows_loss = True
            if key.endswith("rows_after_optimize") and value < measurement(
                key.replace("rows_after_optimize", "rows_before_merge")
            ):
                shows_loss = True
            if key.endswith("one_insert.rows") and value < 2:
                shows_loss = True
        assert shows_loss, (
            f"{store.name} claims to lose history and none of its measurements "
            f"{store.evidence} shows a loss, so the claim is unchecked in the direction nobody "
            f"thinks to check"
        )


def test_the_design_this_repository_used_to_recommend_is_kept_as_an_exhibit() -> None:
    """The wrong answer stays beside the right one, and its cost is a number.

    Deleting it would leave a reader unable to tell that the obvious refinement of the obvious
    design is still wrong, which is the more useful half of the finding.
    """
    by_date = next(store for store in STORES if "where vintage is a DATE" in store.name)
    assert measurement("vintage_as_a_date.rows_after_optimize") == 1, (
        "two versions released on the same day now survive a date-only key, so this exhibit no "
        "longer holds"
    )
    destroyed = measurement("whole_corpus.destroyed_by_a_date_key")
    assert destroyed > 0
    assert str(destroyed) in by_date.measured, (
        f"the entry does not quote the number of values it destroys, {destroyed}, so a reader "
        f"has to take the severity on trust"
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
