"""The whole argument in one screen, read from committed CSV files and nothing else.

    uv run python examples/what_the_publisher_changed.py

NO ENGINE, NO NETWORK, NO CREDENTIAL. Every measurement in this repository needs ClickHouse, or
DuckDB, or an S3 endpoint, or a PostgreSQL, and all of them are worth running. None of them is
worth requiring of somebody who has just cloned this and wants to know what it is about, so this
reads the four committed series with the standard library and prints what the publisher did.

Every figure below is computed here. There are no constants in this file except the series and
the period being followed, which are named because a demo has to point somewhere.
"""

from __future__ import annotations

import csv
import json
import pathlib
from collections import defaultdict

VINTAGES = pathlib.Path(__file__).resolve().parents[1] / "src" / "quarryz" / "data" / "vintages"
SERIES = "IKBJ"
PERIOD = "2021"
WITHDRAWN = "WITHDRAWN"


def rows(cdid: str) -> list[dict[str, str]]:
    with (VINTAGES / f"{cdid}.csv").open(encoding="utf-8", newline="") as handle:
        return sorted(csv.DictReader(handle), key=lambda row: (row["released"], row["version"]))


def as_at(history: list[dict[str, str]], moment: str) -> str:
    """The as-of query, in the only form that is defensible: the last state at or before a date.

    Ordered by the PAIR and not by the release date, because the publisher can issue two
    versions on one morning and this corpus contains mornings where it did.
    """
    seen = [row for row in history if row["released"][: len(moment)] <= moment]
    return seen[-1]["value"] if seen else "not yet published"


def main() -> None:
    corpus = {path.stem: rows(path.stem) for path in sorted(VINTAGES.glob("*.csv"))}
    changes = sum(len(found) for found in corpus.values())
    wrote = sum(len({row["version"] for row in found}) for found in corpus.values())
    source = json.loads((VINTAGES / "SOURCE.json").read_text(encoding="utf-8"))
    walked = sum(entry["versions"] for entry in source["series"])

    # TWO COUNTS AND NOT ONE, because they are not the same number and the first draft of this
    # line called the smaller one "versions walked". The capture walks every published version;
    # a CSV row exists only where a value changed, so a version that republished the same
    # numbers leaves no trace in the corpus at all.
    print(
        f"{len(corpus)} series, {walked} versions walked, {wrote} of which changed at least "
        f"one number, {changes:,} recorded changes. Nothing here is fetched."
    )
    print()

    history = [row for row in corpus[SERIES] if row["period"] == PERIOD]
    print(f"Every value {SERIES} has carried for {PERIOD}, and when it said so:")
    print()
    print(f"  {'released':<12}{'version':<10}{'value':>12}")
    for row in history:
        print(f"  {row['released']:<12}{row['version']:<10}{row['value']:>12}")
    print()

    numeric = [row for row in history if row["value"] != WITHDRAWN]
    moves = [
        (abs(int(float(b["value"])) - int(float(a["value"]))), b["released"])
        for a, b in zip(numeric, numeric[1:])
    ]
    largest, when = max(moves)
    print(
        f"  The largest single move is {largest:,}, on {when}. The period did not change. "
        f"The publisher did."
    )
    print()

    for moment in ("2023-06", "2023-12"):
        print(f"  as at {moment}   {as_at(history, moment):>10}")
    print()

    print("What one line of DDL decides, counted over all four series:")
    print()
    by_pair: set[tuple[str, str, str, str]] = set()
    by_date: set[tuple[str, str, str]] = set()
    by_period: set[tuple[str, str]] = set()
    for cdid, found in corpus.items():
        for row in found:
            by_pair.add((cdid, row["period"], row["released"], row["version"]))
            by_date.add((cdid, row["period"], row["released"]))
            by_period.add((cdid, row["period"]))
    print(f"  keyed on (series, period)                     keeps {len(by_period):>6,}")
    print(f"  keyed on (series, period, vintage as a Date)  keeps {len(by_date):>6,}")
    print(f"  keyed on (series, period, vintage, version)   keeps {len(by_pair):>6,}")
    print(
        f"  The middle row is not a rounding difference. It is "
        f"{len(by_pair) - len(by_date)} published values, deleted with no error."
    )
    print()

    collisions: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in corpus[SERIES]:
        collisions[(SERIES, row["period"], row["released"])].append(row)
    example = next(
        found
        for found in collisions.values()
        if len(found) > 1 and len({row["value"] for row in found}) > 1
    )
    print("Because a release date is not a key. One morning, one period, two published values:")
    print()
    for row in example:
        print(
            f"  {row['released']}  {row['version']:<6}{row['value']:>10}   "
            f"({row['period']}, {SERIES})"
        )


if __name__ == "__main__":
    main()
