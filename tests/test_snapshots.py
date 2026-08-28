"""A snapshot is not a vintage, asserted against what the Iceberg table actually did.

The offline half reads what `scripts/measure_snapshots.py` recorded, so it checks something real
on a machine with no S3 and no Iceberg installed. The measurement itself needs moto, pyiceberg
and pyarrow, and it has its own CI job for that reason.

THE ONE CLAIM WORTH BREAKING. If loading the same corpus twice ever stopped producing a new
snapshot, this repository's thesis would be weaker and the README would need rewriting rather
than the test relaxing. So the count of snapshots against the count of loads is asserted, not
described.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "snapshots"


def summary() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    return loaded


def transcript() -> str:
    return (EVIDENCE / "three-loads.txt").read_text(encoding="utf-8")


def test_loading_the_same_data_again_makes_a_snapshot_and_no_new_version() -> None:
    """The thesis, as two numbers.

    The table's clock moved because we loaded. The publisher's clock did not move because the
    publisher did nothing. Anyone using the first to answer a question about the second gets an
    answer, and it is about the wrong thing.
    """
    numbers = summary()
    first = numbers["by_snapshot"]["load_1_june"]
    again = numbers["by_snapshot"]["load_2_same_data_again"]
    assert first == again, (
        f"loading the same corpus twice changed the value from {first} to {again}, which means "
        f"the two loads were not the same data and the exhibit is measuring something else"
    )
    assert numbers["snapshots"] > numbers["loads"], (
        f"{numbers['loads']} loads produced {numbers['snapshots']} snapshots. If a load ever "
        f"stops producing a snapshot of its own, this repository's argument changes and the "
        f"README needs rewriting rather than this test relaxing"
    )


def test_an_overwrite_is_two_snapshots_and_not_one() -> None:
    """A retention rule counting one snapshot per logical write is already wrong.

    Three loads produce five snapshots here: one append, then a delete and an append for each
    overwrite. Anybody expiring "the last N snapshots" is expiring half as many writes as they
    think.
    """
    operations = summary()["operations"]
    assert operations.count("append") == 3, operations
    assert operations.count("delete") == 2, operations
    assert len(operations) == summary()["snapshots"]


def test_the_table_and_the_publisher_agree_when_asked_the_same_question() -> None:
    """The point is not that the table lies. It is that it answers a different question.

    Asked what it held after the December load, the table says the revised figure. Asked what
    the publisher had said by December, the data says the same. They agree HERE, and load 2 is
    where they come apart: a snapshot with no publication behind it.
    """
    numbers = summary()
    assert numbers["by_snapshot"]["load_3_december"] == numbers["by_vintage"]["as_at_2023_12"]
    assert numbers["by_snapshot"]["load_1_june"] == numbers["by_vintage"]["as_at_2023_06"]
    assert numbers["by_vintage"]["as_at_2023_06"] != numbers["by_vintage"]["as_at_2023_12"], (
        "the two vintages carry the same value, so there is no revision in this corpus and the "
        "comparison shows nothing"
    )


def test_the_measurement_reached_a_real_s3_endpoint() -> None:
    """A pyiceberg misconfiguration writing locally would give a green run proving nothing.

    The harness fails if the bucket is empty or if a warehouse directory appears on disk, and
    the object count is recorded so that a reader can see the check was made rather than being
    told it was.
    """
    assert summary()["objects_in_s3"] > 0
    assert "objects in the bucket" in transcript()
    assert not (REPO / "warehouse").exists(), (
        "a warehouse directory exists in the repository, which is where pyiceberg falls back to "
        "when the S3 endpoint is not reachable"
    )


def test_the_december_corpus_is_not_merely_a_changed_value() -> None:
    """Six months of publication adds periods as well as revising them, which is worth saying.

    A reader comparing two loads should know that the later one is not the earlier one with a
    number altered: it is longer, because the publisher published more periods in between.
    """
    numbers = summary()
    assert numbers["rows_december"] > numbers["rows_june"], (
        f"the December corpus has {numbers['rows_december']} rows against June's "
        f"{numbers['rows_june']}, so nothing new was published in six months, which would be "
        f"surprising enough to check"
    )


def test_the_transcript_shows_the_two_questions_side_by_side() -> None:
    """So a reader sees the difference rather than being told about it."""
    text = transcript()
    assert "what the TABLE held after each" in text
    assert "asked of the DATA rather than of the table" in text
    assert "A snapshot" in text and "records a load" in text
