"""Three engines, one definition, and the tie that decides whether they agree by luck.

The offline half reads what `scripts/measure_agreement.py` recorded. The measurement needs a
ClickHouse binary, DuckDB and a PostgreSQL, and has its own CI job for that reason.

THE CLAIM THIS FILE PROTECTS is not "they agree". Three engines agreeing is easy to arrange by
asking a question none of them can get wrong. What is asserted is that the question was asked at
a moment where one of the idioms CAN get it wrong, and that the number of periods where the
tie-break decided the answer is greater than zero there. Without that, the agreement is a
coincidence dressed as a check.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "agreement"
SCRIPT = REPO / "scripts" / "measure_agreement.py"


def summary() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    return loaded


def moments() -> dict[str, Any]:
    found: dict[str, Any] = summary()["moments"]
    return found


@pytest.mark.parametrize("as_at", ["2023-08", "2016-01"])
def test_the_three_engines_agree_about_every_period(as_at: str) -> None:
    """A disagreement is a finding, not a flake, and the harness exits non-zero on one."""
    moment = moments()[as_at]
    assert moment["disagreements"] == [], moment["disagreements"][:5]
    assert moment["periods_compared"] > 0
    assert moment["period_sets_agree"], (
        "the engines returned different sets of periods, which is a disagreement about what "
        "exists rather than about a value and is worse"
    )


def test_the_agreement_was_tested_where_the_tie_can_decide_it() -> None:
    """The half that makes the agreement worth anything.

    17 periods in this series have a latest release date carrying two versions with different
    values. At 2023-08 later releases have superseded every one of them, so no tie decides
    anything and three engines would agree even if one of them broke ties by coin toss. At
    2016-01 the tie decides 14 periods.
    """
    decided = moments()["2016-01"]["periods_where_the_tie_decided_the_answer"]
    assert len(decided) > 0, (
        "no period is decided by the release-date tie at either moment, so this agreement was "
        "tested only where it cannot fail"
    )
    assert moments()["2023-08"]["periods_where_the_tie_decided_the_answer"] == [], (
        "a tie now decides an answer at 2023-08 as well, which is a change in the corpus worth "
        "reading about before this test is relaxed"
    )


def test_the_clickhouse_query_breaks_the_tie_rather_than_trusting_the_date() -> None:
    """The correction, kept as a check on the file rather than as a memory.

    `argMax(value, released)` has no defined answer when two rows share the largest key. The
    first version of this script used it, and the agreement check passed.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"(released, version)" if tie_break else "released"' in text, (
        "the ClickHouse query no longer chooses between a total and a partial ordering, so the "
        "comparison that found this can no longer be run"
    )


def test_every_engine_orders_by_the_version_and_not_only_the_date() -> None:
    """All three idioms must use the same total order, or agreement is accidental."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count("released desc, version desc") >= 2, (
        "at least one of the DuckDB and PostgreSQL queries orders by the date alone, so it can "
        "return either of two versions published on the same day"
    )


def test_a_period_the_publisher_had_not_reached_is_absent_rather_than_zero() -> None:
    """Asked in 2016 about 2021, the honest answer is that there is no answer."""
    assert moments()["2016-01"]["answer_for_2021"]["clickhouse"] == "absent"
    assert moments()["2023-08"]["answer_for_2021"]["clickhouse"] == "-28039"


def test_the_postgres_key_is_the_pair_and_not_the_release_date() -> None:
    """The reference table has to be able to HOLD two versions from one day, or it is not one."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "primary key (period, released, version)" in text, (
        "the reference table is keyed on the release date, so it would refuse the rows this "
        "repository exists to keep"
    )


def test_the_transcript_says_why_the_wrong_query_looked_right() -> None:
    """A reader should get the finding, not only the numbers."""
    text = (EVIDENCE / "one-question.txt").read_text(encoding="utf-8")
    assert "a query that is wrong is right almost always" in text.lower()
    assert "argMax(value, (released, version))" in text
