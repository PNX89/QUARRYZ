"""The storage choices, as data, and what each one does to a number the publisher changed.

THE ARGUMENT THIS REPOSITORY IS BUILT ON. A revisable number has three clocks attached to it and
they are routinely confused, because two of them look alike and the third is invisible until
somebody asks a question about last quarter.

    VALID TIME       the period the observation is about. 2021, or April 1997.
    TRANSACTION TIME the version the publisher released, which is when WE could first have
                     known. Not a date: 12 series-and-date pairs in this corpus, across 10
                     distinct dates, carry two versions.
    SNAPSHOT TIME    when OUR table changed. An Iceberg snapshot, a git commit, a backup.

THE NUMBER IN THIS FILE WAS FROM THE WRONG POPULATION, and the same mistake was already found
and written up next door before it was found here.

Three sentences below put that figure at 28, described as dates carrying two versions.
Recomputed from the committed CSVs, the corpus has 12 series-and-date pairs carrying two
versions, on 10 distinct dates, split DZLS 3, IKBJ 2, KAC3 4, MGRZ 3.

(The old wording is deliberately not quoted verbatim here. The test that pins this recomputation
also refuses the old sentence, and a note quoting it would fail the guard it is explaining, which
is a trap this portfolio has now walked into three times.) The 2 for IKBJ is the same 2 that
`tests/test_agreement.py` has always asserted, so one file in this repository was right about
the corpus while this one, the file the README sends a reader to first, was not.

`scripts/measure_agreement.py` carries the identical correction about a different figure: it
once said 15 where the truth was 17, and its comment explains that 15 "is true of the
publisher's version WALK and not of this table". A number counted over the publisher's release
history is not a number about the rows that reached disk, because a second version that changed
no value never appears in a corpus recording changes. That lesson was learned in one file and
not carried to its neighbour, which is the only interesting thing about this defect.

`tests/test_stores.py` recomputes the figure now, so it cannot drift again.

Snapshot time is the one that gets used as a substitute for transaction time, because a
warehouse has it for free and it is superficially the same shape. It is not the same fact. A
snapshot records when we loaded something; a version records when the publisher said something.
They coincide only when the load is instantaneous and never repeated, which is never.

WHAT EACH STORE COSTS, MEASURED. The entries below are checked against
`docs/evidence/collapse/summary.json` by tests/test_stores.py, so a claim here that the engine
does not make is a red build rather than a paragraph. The first entry is the one worth reading:
it is what a competent person reaches for, and it deletes the history.

AND THE THIRD ENTRY IS THE ONE I GOT WRONG, which is worth reading second. This file used to
offer `ORDER BY (series, period, vintage)` as the cure and say it lost nothing. It loses 71
published values out of 23,943 in the committed corpus, because a vintage stored as a DATE is
not a unique key and this repository says so in four other places, including nine lines above
this paragraph. The wrong design is kept here beside the right one rather than quietly replaced,
because a repository arguing that an unstated boundary is a claim nobody made cannot silently
correct its own.

WHAT IS DELIBERATELY NOT HERE. Nothing about scale, concurrency, or how any of this behaves
with more than one writer. One process loads a committed corpus of 23,943 rows, and a store that
is right at that size may be wrong at a size this repository never runs.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CLOCKS", "STORES", "Clock", "Store", "as_of", "published_after"]


@dataclass(frozen=True, slots=True)
class Clock:
    """One of the three times attached to a revisable number."""

    name: str
    #: What it answers, in the form of the question a person actually asks.
    answers: str
    #: The mistake made by using it in place of another, and which other.
    confused_with: str


CLOCKS: tuple[Clock, ...] = (
    Clock(
        name="valid time",
        answers="which period is this number about",
        confused_with="nothing, usually. It is the one clock everybody records, because it is "
        "the only one visible in a spreadsheet of the data",
    ),
    Clock(
        name="transaction time",
        answers="when could we first have known this number",
        confused_with="the release date alone, which is not unique: 12 series-and-date pairs "
        "in this corpus carry two versions each, so a table keyed on the date silently merges "
        "two states of the world",
    ),
    Clock(
        name="snapshot time",
        answers="when did OUR table change",
        confused_with="transaction time, and this is the mistake the repository is named for. A "
        "snapshot records a load and a version records a publication. Reloading unchanged data "
        "creates a snapshot and no version; a publisher revising a number a year after we last "
        "loaded creates a version we have no snapshot for until we look",
    ),
)


@dataclass(frozen=True, slots=True)
class Store:
    """One way to hold revisable data, and what it does to the history."""

    #: Named precisely enough to build, not described.
    name: str
    #: What survives in it.
    keeps: str
    #: The question it cannot answer, stated as a question.
    cannot_answer: str
    #: Whether it loses any published value at all. A BOOLEAN AND NOT A PHRASE, because the
    #: field below was carrying both meanings and a guard reading it could not tell them apart:
    #: "nothing at all" in `loss_decided_by` means no scheduler decides the moment, and the
    #: batch-load entry that says it loses everything IMMEDIATELY starts with the same word as
    #: the entry that loses nothing ever. Prose is not a predicate.
    loses_history: bool
    #: What decides the moment history is lost. "Nothing" is a legitimate answer and the point
    #: of the field: for two of these it is not the data and not the query.
    loss_decided_by: str
    #: What was actually read, from docs/evidence. Every entry is joined to a measurement.
    measured: str
    #: The keys in the evidence summary that back the entry, so the join is total rather than
    #: a hand-written list a new entry can be left out of.
    evidence: tuple[str, ...]


STORES: tuple[Store, ...] = (
    Store(
        name="ReplacingMergeTree keyed on (series, period)",
        loses_history=True,
        keeps="the latest value for each observation, and nothing else",
        cannot_answer="what did the publisher say about this period before the revision",
        loss_decided_by="merge scheduling, and how much unrelated data has arrived since. Not "
        "the data being queried and not the query",
        measured="two vintages inserted separately read as 2 rows before any merge and 1 row "
        "after OPTIMIZE TABLE ... FINAL. The same unchanged query, two answers. Across the whole "
        "committed corpus this key keeps 2,533 of 23,943 rows",
        evidence=(
            "naive_key.rows_before_merge",
            "naive_key.rows_after_optimize",
            "whole_corpus.kept_by_a_period_key",
        ),
    ),
    Store(
        name="ReplacingMergeTree keyed on (series, period), loaded in one batch",
        loses_history=True,
        keeps="the latest value, and it never held anything else",
        cannot_answer="the same question, and here there was never a moment at which it could "
        "have been answered",
        loss_decided_by="nothing at all. It happens at write time, in one part, with no merge "
        "involved and nothing to schedule",
        measured="both vintages in a single INSERT produce 1 row in 1 active part. The earlier "
        "value was never written to disk. The corpus figure is the same 2,533: what changes is "
        "when the history goes, not how much of it",
        evidence=(
            "one_insert.rows",
            "one_insert.active_parts",
            "whole_corpus.kept_by_a_period_key",
        ),
    ),
    Store(
        name="ReplacingMergeTree keyed on (series, period, vintage) where vintage is a DATE",
        loses_history=True,
        keeps="every version EXCEPT the ones a publisher released on the same day as another",
        cannot_answer="what the first of two versions published on one day said, because it is "
        "not there to be asked",
        loss_decided_by="the publisher publishing twice in a day, which they do: 12 "
        "series-and-date pairs in this corpus carry two versions each",
        measured="IKBJ period 2015 APR was published twice on 2016-01-08, as -2548 and -2584. "
        "Loaded into this design both rows produce ONE row and the earlier value is gone. Across "
        "the whole committed corpus a date-only key keeps 23,872 of 23,943 rows and destroys 71 "
        "published values",
        evidence=(
            "vintage_as_a_date.rows_after_optimize",
            "whole_corpus.kept_by_a_date_key",
            "whole_corpus.destroyed_by_a_date_key",
        ),
    ),
    Store(
        name="ReplacingMergeTree keyed on (series, period, vintage, version)",
        loses_history=False,
        keeps="every version of every observation, as distinct rows",
        cannot_answer="nothing this repository asks of it",
        loss_decided_by="nothing. The rows are distinct keys and there is nothing to collapse",
        measured="the same two same-day versions both survive an explicit OPTIMIZE, and argMax "
        "over the PAIR answers -2548 at v3 and -2584 at v4. The whole corpus goes in and comes "
        "out at 23,943 rows",
        evidence=(
            "vintage_and_version.rows",
            "vintage_and_version.as_of_v3",
            "vintage_and_version.as_of_v4",
            "whole_corpus.kept_by_a_pair_key",
        ),
    ),
)


def published_after(version: str) -> tuple[int, int]:
    """Ordering over version labels, which are `v<number>` or `current`.

    NUMERIC AND NOT LEXICAL, because "v9" is greater than "v10" as strings. On the morning a
    publisher issues either side of a round ten, a lexical comparison answers with the earlier
    version. No pair in the committed corpus has that shape, so this ordering and a lexical one
    agree on every version actually present and a revert to comparing the labels would change no
    answer here. That is the reason it is pinned by a test rather than left to the data.

    `current` is the live document and therefore the newest. It carries the latest release date
    of every series in this corpus, so it never has to break a tie, and giving it a rank rather
    than a number is what keeps that true if it ever does.
    """
    return (1, 0) if version == "current" else (0, int(version[1:]))


def as_of(
    rows: list[tuple[str, str, str, str]],
    period: str,
    known_by: str,
) -> tuple[str, str, str] | None:
    """What the publisher had said about `period` by `known_by`, and which version said it.

    `rows` are (period, value, released, version) quadruples in any order. The return is the
    value, the release date and the version label, or None when the publisher had said nothing
    yet, which is a different answer from a value of zero and from a withdrawal.

    THE VERSION IS IN THE TUPLE, and taking it out is the defect this whole repository is
    about. This function used to accept (period, value, released) triples and keep the LAST row
    satisfying the bound, so at a release date carrying two versions the answer was decided by
    the caller's list order: IKBJ 2015 APR was published twice on 2016-01-08, at -2548 and then
    -2584, and swapping those two rows swapped the answer. Its stated precondition was "oldest
    first", which two rows carrying the same date satisfy in either order, so a caller had no
    way to sort into a compliant order out of the data the signature accepted. The repository
    proves the same defect in ClickHouse three files away and calls `argMax(value, released)`
    undefined at a tie; the Python here keyed on the date and hoped.

    So nothing is assumed about the order. The answer is the largest (released, version) at or
    before the bound, which is the same key `dbt/models/warehouse.sql` and all three engines in
    `scripts/measure_agreement.py` order on.

    THE DATE COMPARISON IS ON THE PREFIX, deliberately. A caller asking as at "2023" means the
    end of 2023, and a caller asking as at "2023-10" means the end of that month. A lexical
    prefix comparison over ISO dates gets both right, and a naive `<=` against a string of a
    different length gets the first one wrong in a way that is invisible until somebody asks a
    question about a year.
    """
    best: tuple[tuple[str, tuple[int, int]], tuple[str, str, str]] | None = None
    for row_period, value, released, version in rows:
        if row_period != period:
            continue
        if released[: len(known_by)] > known_by:
            continue
        ranked = (released, published_after(version))
        if best is None or ranked > best[0]:
            best = (ranked, (value, released, version))
    return best[1] if best else None
