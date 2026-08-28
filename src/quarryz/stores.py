"""The storage choices, as data, and what each one does to a number the publisher changed.

THE ARGUMENT THIS REPOSITORY IS BUILT ON. A revisable number has three clocks attached to it and
they are routinely confused, because two of them look alike and the third is invisible until
somebody asks a question about last quarter.

    VALID TIME       the period the observation is about. 2021, or April 1997.
    TRANSACTION TIME the version the publisher released, which is when WE could first have
                     known. Not a date: 28 dates in this corpus carry two versions.
    SNAPSHOT TIME    when OUR table changed. An Iceberg snapshot, a git commit, a backup.

Snapshot time is the one that gets used as a substitute for transaction time, because a
warehouse has it for free and it is superficially the same shape. It is not the same fact. A
snapshot records when we loaded something; a version records when the publisher said something.
They coincide only when the load is instantaneous and never repeated, which is never.

WHAT EACH STORE COSTS, MEASURED. The entries below are checked against
`docs/evidence/collapse/summary.json` by tests/test_stores.py, so a claim here that the engine
does not make is a red build rather than a paragraph. The first entry is the one worth reading:
it is what a competent person reaches for, and it deletes the history.

WHAT IS DELIBERATELY NOT HERE. Nothing about scale, concurrency, or how any of this behaves
with more than one writer. One process loads a committed corpus of 23,943 rows, and a store that
is right at that size may be wrong at a size this repository never runs.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CLOCKS", "STORES", "Clock", "Store", "as_of"]


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
        confused_with="the release date alone, which is not unique: 28 dates in this corpus "
        "carry two versions each, so a table keyed on the date silently merges two states of "
        "the world",
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
        keeps="the latest value for each observation, and nothing else",
        cannot_answer="what did the publisher say about this period before the revision",
        loss_decided_by="merge scheduling, and how much unrelated data has arrived since. Not "
        "the data being queried and not the query",
        measured="two vintages inserted separately read as 2 rows before any merge and 1 row "
        "after OPTIMIZE TABLE ... FINAL. The same unchanged query, two answers",
        evidence=("naive_key.rows_before_merge", "naive_key.rows_after_optimize"),
    ),
    Store(
        name="ReplacingMergeTree keyed on (series, period), loaded in one batch",
        keeps="the latest value, and it never held anything else",
        cannot_answer="the same question, and here there was never a moment at which it could "
        "have been answered",
        loss_decided_by="nothing at all. It happens at write time, in one part, with no merge "
        "involved and nothing to schedule",
        measured="both vintages in a single INSERT produce 1 row in 1 active part. The earlier "
        "value was never written to disk",
        evidence=("one_insert.rows", "one_insert.active_parts"),
    ),
    Store(
        name="ReplacingMergeTree keyed on (series, period, vintage)",
        keeps="every version of every observation, as distinct rows",
        cannot_answer="which of two versions published on the same day came second, unless the "
        "version label is in the key as well as the date",
        loss_decided_by="nothing. The rows are distinct keys and there is nothing to collapse",
        measured="the same two vintages survive an explicit OPTIMIZE, and argMax over them "
        "answers 100.0 asked as at 2020 and 105.5 asked as at 2021",
        evidence=("vintage_in_key.rows", "vintage_in_key.as_of_2020", "vintage_in_key.as_of_2021"),
    ),
)


def as_of(
    rows: list[tuple[str, str, str]],
    period: str,
    known_by: str,
) -> tuple[str, str] | None:
    """What the publisher had said about `period` by `known_by`, with the version that said it.

    `rows` are (period, value, released) triples, oldest first. The return is the value and the
    release date it came from, or None when the publisher had said nothing yet, which is a
    different answer from a value of zero and from a withdrawal.

    THE COMPARISON IS ON THE PREFIX OF THE DATE, deliberately. A caller asking as at "2023"
    means the end of 2023, and a caller asking as at "2023-10" means the end of that month. A
    lexical prefix comparison over ISO dates gets both right, and a naive `<=` against a string
    of a different length gets the first one wrong in a way that is invisible until somebody
    asks a question about a year.
    """
    seen: tuple[str, str] | None = None
    for row_period, value, released in rows:
        if row_period != period:
            continue
        if released[: len(known_by)] <= known_by:
            seen = (value, released)
    return seen
