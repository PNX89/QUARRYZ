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
import re
from typing import Any

import pytest

from quarryz.stores import CLOCKS, STORES, Store, as_of, published_after

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


def published(cdid: str) -> list[tuple[str, str, str, str]]:
    """The corpus in the shape as_of takes it: period, value, release date and VERSION."""
    with (VINTAGES / f"{cdid}.csv").open(encoding="utf-8", newline="") as handle:
        return [
            (row["period"], row["value"], row["released"], row["version"])
            for row in csv.DictReader(handle)
        ]


def sort_key(text: str) -> str:
    """The DDL tuple inside a design's name, which is the thing that distinguishes the four.

    Matched rather than the whole name, so the surrounding prose can be reworded on either side
    of the join without the join becoming a transcription of it.
    """
    found = re.search(r"\(series[^)]*\)", text)
    assert found, f"no sort key in {text!r}, so there is nothing to compare it by"
    return " ".join(found.group(0).split())


def test_the_four_designs_are_the_four_the_readme_offers() -> None:
    """A PARAMETRISED SET READ OUT OF THE CODE UNDER TEST IS NOT A CHECK ON THAT SET.

    Every other test in this file iterates STORES, so deleting an entry deletes the checking of
    it and the suite goes green one case lighter, which reads exactly like a pass. Removing the
    fourth entry, the design the README table and the published card both advertise, failed one
    test: the card's stated test total. Its message says to re-run capture_evidence.py, and
    doing what the message says leaves this repository recommending a design that the file
    carrying the designs no longer holds.

    So the set is pinned by size and by sort key, and joined to the README's key table, which is
    where a reader meets these four. That join is the one this repository already builds between
    its prose and its evidence, applied to the artefact it skipped.
    """
    keys = [sort_key(store.name) for store in STORES]
    assert keys == [
        "(series, period)",
        "(series, period)",
        "(series, period, vintage)",
        "(series, period, vintage, version)",
    ], f"STORES now offers {keys}"

    # The two that share a sort key are not the same claim: one loses the earlier vintage at
    # merge time and the other never writes it at all, which is the harder half to argue.
    batched = [store for store in STORES if "batch" in store.name or "insert" in store.name]
    assert len(batched) == 1, "the two designs keyed on the observation no longer differ by how"

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    offered = [line for line in readme.splitlines() if line.startswith("| `(series")]
    assert offered, "the README no longer carries a key table, so there is nothing to join to"
    assert [sort_key(line) for line in offered] == keys, (
        "the README's key table and STORES no longer describe the same four designs, so a "
        "reader is being offered a storage choice this repository does not measure"
    )


def test_exactly_one_design_is_the_one_this_repository_recommends() -> None:
    """The entry a reader is meant to build, asserted to still be here.

    Nothing else in this file cares which design wins. The tests above check each entry against
    its own evidence, so a table containing only the three that lose history would satisfy every
    one of them while the README went on recommending a fourth.
    """
    recommended = [store for store in STORES if not store.loses_history]
    assert len(recommended) == 1, (
        f"{len(recommended)} designs claim to lose nothing. A table with none of them recommends "
        f"nothing, and a table with two has not decided"
    )
    assert sort_key(recommended[0].name) == "(series, period, vintage, version)", (
        f"the design that loses nothing is now keyed {sort_key(recommended[0].name)}, and the "
        f"whole argument is that the version has to be in the key"
    )


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


def test_the_date_key_exhibit_measures_a_merge_and_not_a_write() -> None:
    """The harness once loaded both same-day rows in one INSERT, so `by_date` started at 1 row
    and OPTIMIZE changed nothing, 1 to 1, while the README and this file's own transcript
    describe the second row overwriting the first AT MERGE TIME, the same mechanism the naive
    exhibit above demonstrates. A harness measuring write-time collapse under a comment claiming
    a merge is the naive table's second exhibit wearing the wrong table's name.

    So this asserts the shape `test_the_obvious_design_loses_a_vintage_and_the_evidence_says_so`
    asserts for the naive table: two rows on disk before OPTIMIZE, one after. Before is the half
    that distinguishes a merge from a write, and nothing checked it.
    """
    before = measurement("vintage_as_a_date.rows_before_merge")
    after = measurement("vintage_as_a_date.rows_after_optimize")
    assert before == 2 and after == 1, (
        f"the date-key table read {before} rows before OPTIMIZE and {after} after, so this "
        f"exhibit is not measuring a merge collapsing two written rows into one"
    )


@pytest.mark.parametrize("store", STORES, ids=lambda s: s.name)
def test_a_corpus_figure_an_entry_names_is_a_figure_it_states(store: Store) -> None:
    """An entry naming a corpus measurement and not stating it makes a reader take it on trust.

    One test below already required this of the date-key exhibit, which was the entry whose
    severity mattered most at the time. The two entries above it have since acquired corpus
    figures of their own, typed into the same prose field, and nothing read them: this table
    could have gone on saying an obvious key keeps 1 row out of 23,943 while naming the
    measurement that says 2,533, which is what the README's key table did for months.
    """
    for key in store.evidence:
        if not key.startswith("whole_corpus."):
            continue
        value = measurement(key)
        assert f"{value:,}" in store.measured, (
            f"{store.name} names {key}, which measured {value:,}, and its own description does "
            f"not state that figure anywhere"
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
    rows = published("IKBJ")
    early = as_of(rows, "2021", "2023-06")
    late = as_of(rows, "2021", "2023-12")
    now = as_of(rows, "2021", "2026")

    assert early is not None and late is not None and now is not None
    assert early[0] == "-28039", early
    assert late[0] == "-3518", late
    assert early[0] != late[0], "the revision is invisible to as_of, which is the one job it has"
    assert late[1] == "2023-10-11"


def test_as_of_breaks_a_same_day_tie_on_the_version_and_not_on_the_caller_order() -> None:
    """THE QUESTION THIS REPOSITORY EXISTS FOR, and every test here used to ask the easy one.

    All four as_of tests asked about IKBJ 2021, which has no tie, so this file reproduced the
    exact failure the README congratulates the repository for escaping: the check only ever
    asked the question that could not go wrong. Under the old signature the version was not in
    the tuple at all, the loop kept whichever qualifying row came last, and the publisher's
    order was therefore decided by the caller's list order.

    The publisher released 2015 APR twice on 2016-01-08, at -2548 and then -2584. -2548 is the
    value docs/evidence/collapse records as destroyed by a date-only key, so an as-of query that
    answers with it at this moment is making the same mistake the storage layer is measured for.
    """
    rows = published("IKBJ")
    tied = [row for row in rows if row[0] == "2015 APR" and row[2] == "2016-01-08"]
    assert len(tied) == 2, (
        f"2015 APR is no longer published twice on 2016-01-08, so this corpus cannot ask a tied "
        f"question and the claim has to move rather than this test relaxing: {tied}"
    )
    assert len({row[1] for row in tied}) == 2, (
        "the two versions published that morning now carry the same value, so the tie decides "
        "nothing and this is the easy question again"
    )

    answer = as_of(rows, "2015 APR", "2016-01-08")
    assert answer == ("-2584", "2016-01-08", "v4"), (
        f"as at 2016-01-08 the publisher's last word on 2015 APR was v4 at -2584, and as_of "
        f"answered {answer}"
    )

    # THE SAME ROWS IN TWO OTHER ORDERS. Both satisfy the old "oldest first" precondition,
    # because the two tied rows carry the same date, and under the old implementation the
    # swapped one answered -2548.
    swapped = list(rows)
    left, right = rows.index(tied[0]), rows.index(tied[1])
    swapped[left], swapped[right] = swapped[right], swapped[left]
    assert as_of(swapped, "2015 APR", "2016-01-08") == answer, (
        "swapping two rows carrying the same period and the same release date changed the "
        "answer, so which version the publisher issued second is being decided by list order"
    )
    assert as_of(list(reversed(rows)), "2015 APR", "2016-01-08") == answer


def test_as_of_orders_versions_as_numbers_and_not_as_labels() -> None:
    """A LATENT DEFECT PINNED BY A CONSTRUCTED PAIR, because the corpus cannot ask it.

    Every same-day pair in these four series is v2/v3, v3/v4 or v97/v98, and on all of them a
    lexical comparison of the labels and a numeric one agree. So the ordering could be reverted
    to a plain `max()` over the strings and no answer in this repository would change, which is
    the shape of defect that ships: correct output from a mechanism nobody can rely on.

    The same reasoning is written down two files away about `float("3.9") > float("3.13")`
    ordering a published Python range backwards, and it is the same mistake: a version is a
    tuple of integers, not a string and not a decimal.

    Asked of a constructed pair rather than of the corpus, and said plainly: the corpus contains
    no release date carrying a v9 and a v10, so there is no honest way to ask it there.
    """
    assert published_after("v10") > published_after("v9")
    assert published_after("current") > published_after("v999")

    same_morning = [
        ("2020 JAN", "100", "2021-03-01", "v9"),
        ("2020 JAN", "105", "2021-03-01", "v10"),
    ]
    assert as_of(same_morning, "2020 JAN", "2021-03") == ("105", "2021-03-01", "v10")
    assert as_of(list(reversed(same_morning)), "2020 JAN", "2021-03") == (
        "105",
        "2021-03-01",
        "v10",
    )


def test_as_of_says_nothing_rather_than_zero_before_the_publisher_spoke() -> None:
    """A period nobody had published yet is not a zero and not a missing key."""
    rows = published("IKBJ")
    assert as_of(rows, "2021", "2015") is None


def test_as_of_compares_a_year_correctly_and_not_by_string_length() -> None:
    """The bug this function is written to avoid, asserted rather than commented.

    A caller asking as at "2023" means the end of 2023. Comparing that against "2023-10-11" with
    a plain `<=` puts the release AFTER the question, because "2023-10-11" > "2023" lexically,
    so the October revision would be invisible to anyone asking about the year.
    """
    rows = published("IKBJ")
    by_year = as_of(rows, "2021", "2023")
    by_day = as_of(rows, "2021", "2023-12-31")
    assert by_year is not None and by_day is not None
    assert by_year[0] == by_day[0] == "-3518", (
        f"asking as at a year gave {by_year} and asking as at that year's last day gave "
        f"{by_day}, so the comparison is being done on string length rather than on the date"
    )


def test_a_withdrawal_comes_back_as_a_withdrawal_and_not_as_a_number() -> None:
    """The publisher emptied a value. as_of must say so rather than skipping to the last number."""
    rows = published("IKBJ")
    withdrawn = [(period, released) for period, value, released, _ in rows if value == "WITHDRAWN"]
    assert withdrawn, "no withdrawal in the corpus, so this cannot be tested here"
    period, released = withdrawn[0]
    answer = as_of(rows, period, released)
    assert answer is not None and answer[0] == "WITHDRAWN", (
        f"as at {released} the publisher had withdrawn {period}, and as_of answered {answer}"
    )


def test_the_two_version_figure_is_recomputed_from_the_corpus() -> None:
    """Three sentences in stores.py said 28. The corpus has 12.

    THE INTERESTING PART IS THAT THIS REPOSITORY ALREADY KNEW. `scripts/measure_agreement.py`
    carries the same correction about a different figure, where it once said 15 and the truth was
    17, and its comment explains why: 15 was "true of the publisher's version WALK and not of
    this table". A count over the publisher's release history is not a count of the rows that
    reached disk, because a second version that changed no value never enters a corpus that
    records changes.

    That lesson was written down in one file and not carried to its neighbour, and the neighbour
    is the file the README tells a reader to open first.

    Recomputed here rather than pinned, so the sentence and the data cannot part company again.
    """
    import csv
    from collections import defaultdict

    vintages = REPO / "src" / "quarryz" / "data" / "vintages"
    versions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for path in sorted(vintages.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                versions[(path.stem, row["released"])].add(row["version"])

    colliding = [key for key, seen in versions.items() if len(seen) > 1]
    pairs = len(colliding)
    dates = len({key[1] for key in colliding})

    source = (REPO / "src" / "quarryz" / "stores.py").read_text(encoding="utf-8")
    flat = " ".join(source.split())

    assert f"{pairs} series-and-date pairs" in flat, (
        f"the corpus has {pairs} series-and-date pairs carrying two versions and stores.py does "
        f"not say so. A number in the file a reader opens first has parted company with the data"
    )
    assert f"across {dates}" in flat, f"the collisions fall on {dates} distinct dates"
    assert "28 dates in this corpus" not in flat, (
        "the publisher-walk figure is back. It counts release events, not rows on disk, and the "
        "two differ because a version that changed no value never enters this corpus"
    )

    # The per-series split, so a corpus swap that preserved the total would still be caught.
    per = {series: sum(1 for k in colliding if k[0] == series) for series, _ in colliding}
    assert per == {"DZLS": 3, "IKBJ": 2, "KAC3": 4, "MGRZ": 3}, per
    # And the IKBJ figure is the one tests/test_agreement.py has always asserted separately.
    assert per["IKBJ"] == 2
