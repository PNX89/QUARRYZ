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


def test_what_a_write_costs_in_snapshots_depends_on_its_shape() -> None:
    """A CORRECTION. This asserted "an overwrite is two snapshots, a delete and an append".

    That is true of a FULL overwrite of a non-empty table and of nothing else, and it was
    generalised from the single case this exhibit happens to perform. Measured on the same
    pyiceberg against the same table, three shapes of write give three different answers:

        overwrite of an empty table   append
        overwrite with a filter       append, overwrite, append
        full overwrite, twice         append, delete, append, delete, append

    The filtered form is what an incremental loader actually writes, and it produces no delete
    at all, so a retention rule keyed on counting deletes would have been wrong about the
    commonest case. The useful claim survives and is smaller: a snapshot is not a logical write,
    and how many you get is a property of the call rather than of the load.
    """
    variants = summary()["overwrite_variants"]
    assert variants["overwrite_of_an_empty_table"] == ["append"]
    assert variants["overwrite_with_a_filter"] == ["append", "overwrite", "append"]
    assert variants["full_overwrite_twice"] == [
        "append",
        "delete",
        "append",
        "delete",
        "append",
    ]
    assert len({tuple(shape) for shape in variants.values()}) == 3, (
        "two shapes of write now produce the same snapshot sequence, so the claim that the cost "
        "depends on the shape is no longer supported by these measurements"
    )
    assert len(summary()["operations"]) == summary()["snapshots"]


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


def test_the_transcript_prints_the_measured_shapes_rather_than_a_sentence_about_them() -> None:
    """A RETRACTION THAT REACHED THREE FILES AND NOT THE FOURTH.

    The test above is labelled A CORRECTION: the claim that an overwrite costs a delete and an
    append is true of a full overwrite of a populated table and of nothing else, and the summary
    beside this transcript records the filtered form as append, overwrite, append, with no
    delete in it at all. That retraction was applied to summary.json, to that test and to the
    README, and the line the harness printed into the transcript was left standing, so the
    committed evidence contradicted the summary in its own directory.

    (The withdrawn wording is deliberately not quoted here. This guard forbids it in a
    transcript, and a guard whose own file carries the thing it forbids is a trap this portfolio
    has walked into more than once.)

    The sentence is gone and the measured shapes are printed, which is the only version that
    cannot outlive the measurement. Both directions are checked: every shape reaches the page
    with the operations it was measured to cost, and no other line describes what an overwrite
    costs, because that is where a generalisation gets back in.
    """
    lines = transcript().splitlines()
    variants = summary()["overwrite_variants"]
    assert len(variants) > 1, "one shape of write cannot show that the cost depends on the shape"

    for shape, operations in variants.items():
        wanted = ", ".join(operations)
        assert any(shape in line and wanted in line for line in lines), (
            f"the transcript does not show {shape} costing {wanted}, so the page and the "
            f"summary beside it describe different runs"
        )

    printed = {line for line in lines if any(shape in line for shape in variants)}
    for line in lines:
        if line in printed or "overwrite" not in line.lower():
            continue
        assert not any(word in line.lower() for word in ("delete", "append")), (
            f"a line of the transcript says what an overwrite costs outside the measured table, "
            f"which is how the generalisation got in the first time: {line.strip()!r}"
        )


def test_the_transcript_shows_the_two_questions_side_by_side() -> None:
    """So a reader sees the difference rather than being told about it."""
    text = transcript()
    assert "what the TABLE held after each" in text
    assert "asked of the DATA rather than of the table" in text
    assert "A snapshot" in text and "records a load" in text
