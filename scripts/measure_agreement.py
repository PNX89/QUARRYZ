"""One as-of question, asked of three engines in three idioms, and they must agree.

    uv run --group engines python scripts/measure_agreement.py

WHY THIS IS WORTH DOING AT ALL. Every claim this repository makes about what the publisher said
at a moment rests on one query shape, and that shape is written three different ways because the
three engines do not share an idiom:

    ClickHouse   argMax(value, released)
    DuckDB       a window function with row_number
    PostgreSQL   distinct on (period)

Three implementations of one definition is three chances to get it wrong, and the usual way that
goes unnoticed is that only one of them is ever run. So all three are run against the same
committed corpus and every answer is compared. A disagreement is a finding, not a flake, and the
script exits non-zero rather than recording the majority.

THE COMPARISON IS ON EVERY PERIOD, not on the headline one. Agreeing about the number a README
quotes and disagreeing about a period nobody looked at is exactly the failure this is for, so
the check is over the whole series and the count of compared periods is recorded.

WHAT THIS IS NOT. It is not a benchmark and nothing here times anything. Three engines agreeing
about a definition says nothing about which is the right tool, and this repository has no opinion
on that beyond what the collapse measurement already shows.
"""

from __future__ import annotations

import csv
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "agreement"
VINTAGES = ROOT / "src" / "quarryz" / "data" / "vintages"
CLICKHOUSE = ROOT / "bin" / "clickhouse"

SERIES = "IKBJ"
#: TWO MOMENTS, AND THE SECOND ONE IS THE POINT.
#:
#: 2023-08 is chosen because the headline revision falls either side of it, so an engine
#: ignoring the as-of bound answers visibly wrongly rather than subtly.
#:
#: 2016-01 is chosen because it is a moment where the RELEASE DATE TIE DECIDES THE ANSWER. This
#: series has 17 periods whose latest release date carries two versions with different values,
#: and at most cut-offs a later release has superseded them so the tie never decides anything.
#: Asking only at 2023-08 is asking a question the tie cannot answer wrongly.
MOMENTS = ("2023-08", "2016-01")


def rows() -> list[dict[str, str]]:
    with (VINTAGES / f"{SERIES}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def from_clickhouse(as_at: str, tie_break: bool = True) -> dict[str, str]:
    """argMax, which is ClickHouse's idiom for "the value at the largest key".

    THE KEY IS A TUPLE AND NOT THE DATE, and this is the correction that matters most in this
    file. `argMax(value, released)` has no defined answer when two rows share the largest key,
    and 17 periods in this series have exactly that: one release date carrying two versions with
    different values. Measured, the two forms disagree on 14 periods at the 2016-01 cut-off.

    The first version of this script used the date alone and the agreement check passed, because
    it only ever asked at 2023-08 where later releases had superseded every tied period. A query
    that is wrong is right almost all the time, which is why `tie_break=False` is kept: the
    harness runs both and records where they differ rather than describing it.
    """
    key = "(released, version)" if tie_break else "released"
    query = f"""
        select period, argMax(value, {key}) as value
        from file('{VINTAGES / f"{SERIES}.csv"}', CSVWithNames,
                  'period String, value String, released String, version String')
        where substring(released, 1, {len(as_at)}) <= '{as_at}'
        group by period
        format JSONEachRow
    """
    result = subprocess.run(
        [str(CLICKHOUSE), "local", "--query", query],
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        entry["period"]: entry["value"]
        for entry in (json.loads(line) for line in result.stdout.splitlines() if line.strip())
    }


def from_duckdb(as_at: str) -> dict[str, str]:
    """A window function, which is the portable way to say the same thing."""
    import duckdb

    connection = duckdb.connect()
    connection.execute("SET extension_directory = ?", [str(ROOT / "duckdb_ext")])
    found = connection.execute(
        f"""
        select period, value from (
            select period, value,
                   row_number() over (partition by period order by released desc,
                                      version desc) as recency
            from read_csv(?, header = true,
                          columns = {{'period': 'VARCHAR', 'value': 'VARCHAR',
                                     'released': 'VARCHAR', 'version': 'VARCHAR'}})
            where substr(released, 1, {len(as_at)}) <= ?
        ) where recency = 1
        """,
        [str(VINTAGES / f"{SERIES}.csv"), as_at],
    ).fetchall()
    return {str(period): str(value) for period, value in found}


def from_postgres(dsn: str, as_at: str) -> dict[str, str]:
    """distinct on, which is PostgreSQL's own idiom and exists in no other engine here.

    This is the reference table the whole warehouse is checked against, so it is loaded from the
    CSV rather than from either of the other two: an answer key derived from the thing it is
    checking is not an answer key.
    """
    import psycopg

    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("drop table if exists observations")
        cursor.execute(
            """
            create table observations (
                period text not null,
                value text not null,
                released text not null,
                version text not null,
                -- THE KEY IS THE PAIR AND NOT THE DATE. 15 release dates in this series carry
                -- two versions each, so a primary key on (period, released) would refuse rows
                -- that are genuinely different states of the world.
                primary key (period, released, version)
            )
            """
        )
        with cursor.copy("copy observations (period, value, released, version) from stdin") as copy:
            for row in rows():
                copy.write_row((row["period"], row["value"], row["released"], row["version"]))
        cursor.execute(
            """
            select distinct on (period) period, value
            from observations
            where substr(released, 1, %s) <= %s
            order by period, released desc, version desc
            """,
            [len(as_at), as_at],
        )
        return {str(period): str(value) for period, value in cursor.fetchall()}


def compare(dsn: str, as_at: str) -> dict[str, Any]:
    """The three engines at one moment, plus the untie-broken ClickHouse form beside them."""
    answers = {
        "clickhouse": from_clickhouse(as_at),
        "duckdb": from_duckdb(as_at),
        "postgres": from_postgres(dsn, as_at),
    }
    without_tie_break = from_clickhouse(as_at, tie_break=False)

    periods = {name: set(found) for name, found in answers.items()}
    shared = set.intersection(*periods.values())
    if not shared:
        raise SystemExit(f"the engines share no periods at {as_at}, so nothing was compared")

    disagreements = [
        {"period": period, **{name: answers[name][period] for name in answers}}
        for period in sorted(shared)
        if len({answers[name][period] for name in answers}) > 1
    ]
    tie_decided = sorted(
        period
        for period in shared
        if without_tie_break.get(period) != answers["clickhouse"][period]
    )

    return {
        "as_at": as_at,
        "periods_compared": len(shared),
        "periods_per_engine": {name: len(found) for name, found in periods.items()},
        "period_sets_agree": len({tuple(sorted(found)) for found in periods.values()}) == 1,
        "disagreements": disagreements,
        "periods_where_the_tie_decided_the_answer": tie_decided,
        "answer_for_2021": {name: answers[name].get("2021", "absent") for name in answers},
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dsn = os.environ.get("QUARRYZ_POSTGRES", "postgresql://postgres@127.0.0.1:5432/postgres")

    if not CLICKHOUSE.exists():
        print("bin/clickhouse is missing. Run scripts/fetch_tools.sh", file=sys.stderr)
        return 1

    moments = [compare(dsn, as_at) for as_at in MOMENTS]
    summary: dict[str, Any] = {
        "series": SERIES,
        "moments": {entry["as_at"]: entry for entry in moments},
    }

    for entry in moments:
        if entry["disagreements"]:
            print(f"the engines disagree at {entry['as_at']}:", file=sys.stderr)
            for row in entry["disagreements"][:10]:
                print(f"  {row}", file=sys.stderr)
            (OUT / "disagreements.json").write_text(
                json.dumps(entry["disagreements"], indent=2) + "\n", encoding="utf-8"
            )
            return 1
        if not entry["period_sets_agree"]:
            print(
                f"at {entry['as_at']} the engines returned different SETS of periods, which "
                f"is a disagreement about what exists rather than about a value",
                file=sys.stderr,
            )
            return 1

    headline = summary["moments"]["2023-08"]["answer_for_2021"]["clickhouse"]
    if headline != "-28039":
        print(
            f"as at 2023-08 the 2021 balance should still read -28039 and reads {headline}. "
            f"Three engines agreeing on a wrong answer would prove nothing, so this is "
            f"checked separately from their agreement.",
            file=sys.stderr,
        )
        return 1

    decided = summary["moments"]["2016-01"]["periods_where_the_tie_decided_the_answer"]
    if not decided:
        print(
            "no period at 2016-01 is decided by the release-date tie, so the tuple key in the "
            "ClickHouse query is protecting against nothing measurable here and the claim "
            "must be dropped rather than asserted",
            file=sys.stderr,
        )
        return 1

    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    with (OUT / "one-question.txt").open("w", encoding="utf-8") as handle:
        print(f"$ python scripts/measure_agreement.py   # {SERIES}", file=handle)
        print(file=handle)
        print("Three idioms for one definition:", file=handle)
        print("  clickhouse  argMax(value, (released, version))", file=handle)
        print("  duckdb      row_number() over (order by released desc, version desc)", file=handle)
        print(
            "  postgres    distinct on (period) ... order by released desc, version desc",
            file=handle,
        )
        for entry in moments:
            print(file=handle)
            print(f"--- as at {entry['as_at']} ---", file=handle)
            print(
                f"{entry['periods_compared']} periods compared, "
                f"{len(entry['disagreements'])} disagreements",
                file=handle,
            )
            print(f"2021 reads {entry['answer_for_2021']['clickhouse']} in all three", file=handle)
            print(
                f"{len(entry['periods_where_the_tie_decided_the_answer'])} periods where the "
                f"release-date tie decided the answer",
                file=handle,
            )
        print(file=handle)
        print(
            "THE TIE IS THE POINT. This series has release dates carrying two versions with",
            file=handle,
        )
        print(
            "different values. argMax(value, released) has no defined answer there, and at",
            file=handle,
        )
        print(
            f"2016-01 it returns the superseded one for {len(decided)} periods. At 2023-08 it",
            file=handle,
        )
        print("returns the right answer for all of them, because later releases have", file=handle)
        print(
            "superseded every tied period: a query that is wrong is right almost always.",
            file=handle,
        )

    print(json.dumps(summary, indent=2)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
