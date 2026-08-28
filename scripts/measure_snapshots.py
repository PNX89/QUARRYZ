"""An Iceberg snapshot records when WE changed the table. A vintage records when the PUBLISHER
changed the number. This measures the difference on real data.

    uv run --group engines python scripts/measure_snapshots.py

WHY THIS IS THE CENTRAL EXHIBIT. Table time travel is the feature everybody reaches for when
somebody asks "what did this look like last quarter", and it answers a question about OUR table.
The question asked was about the PUBLISHER'S numbers. The two coincide only if every load
happened at the moment of publication and no load was ever repeated, which is never true.

Three loads are performed against a real Iceberg table on a moto S3 endpoint, and each is a
snapshot:

  LOAD 1  the corpus as the publisher had it in June 2023
  LOAD 2  THE SAME DATA AGAIN, unchanged. A new snapshot. No new version.
  LOAD 3  the corpus as at December 2023, which includes the revision

After that, two questions are asked in both directions, and they give different answers:

  by SNAPSHOT   what did our table hold at snapshot N
  by VINTAGE    what had the publisher said as at a date

MOTO IS A REAL S3 ENDPOINT HERE, NOT A MOCK IN THE PROCESS. That distinction is checked rather
than assumed: the run counts the objects in the bucket afterwards and fails if there are none,
because a pyiceberg misconfiguration that silently writes to the local filesystem would produce
a green run proving nothing. It also fails if a warehouse directory appears on disk.

WHAT THIS DOES NOT SHOW. One writer, one table, no concurrent commits, and no catalog other than
a sqlite one. Iceberg's snapshot isolation under contention is not exercised and nothing here is
evidence about it.
"""

from __future__ import annotations

import csv
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "snapshots"
VINTAGES = ROOT / "src" / "quarryz" / "data" / "vintages"

BUCKET = "quarryz-warehouse"
SERIES = "IKBJ"
#: The period whose revision this repository quotes everywhere, and the two moments either side.
PERIOD = "2021"
BEFORE = "2023-06"
AFTER = "2023-12"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def rows_as_at(known_by: str) -> list[dict[str, Any]]:
    """The corpus as the publisher had it at a moment: one row per period, latest version."""
    latest: dict[str, dict[str, Any]] = {}
    with (VINTAGES / f"{SERIES}.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["released"][: len(known_by)] <= known_by:
                latest[row["period"]] = {
                    "period": row["period"],
                    "value": row["value"],
                    "released": row["released"],
                    "version": row["version"],
                }
    return [latest[period] for period in sorted(latest)]


def main() -> int:
    import boto3
    import pyarrow as pa
    from pyiceberg.catalog.sql import SqlCatalog
    from pyiceberg.expressions import EqualTo, Reference
    from pyiceberg.expressions.literals import literal

    OUT.mkdir(parents=True, exist_ok=True)
    work = pathlib.Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "quarryz-snapshots"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    port = free_port()
    endpoint = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "moto.server", "-p", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise SystemExit("moto never started listening")

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id="quarryz",
            aws_secret_access_key="quarryz",
            region_name="eu-west-2",
        )
        s3.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-2"}
        )

        catalog = SqlCatalog(
            "quarryz",
            **{
                "uri": f"sqlite:///{work}/catalog.db",
                "warehouse": f"s3://{BUCKET}/warehouse",
                "s3.endpoint": endpoint,
                "s3.access-key-id": "quarryz",
                "s3.secret-access-key": "quarryz",
                "s3.region": "eu-west-2",
            },
        )
        catalog.create_namespace("ons")

        june = rows_as_at(BEFORE)
        december = rows_as_at(AFTER)
        schema = pa.schema(
            [
                ("period", pa.string()),
                ("value", pa.string()),
                ("released", pa.string()),
                ("version", pa.string()),
            ]
        )

        # LOAD 1. The corpus as at June 2023.
        table = catalog.create_table("ons.trade_balance", schema=schema)
        table.append(pa.Table.from_pylist(june, schema=schema))
        first = table.current_snapshot()
        assert first is not None

        # LOAD 2. THE SAME DATA AGAIN. This is the exhibit: a snapshot with no new version.
        table.overwrite(pa.Table.from_pylist(june, schema=schema))
        table.refresh()
        second = table.current_snapshot()
        assert second is not None

        # LOAD 3. The corpus as at December 2023, which carries the revision.
        table.overwrite(pa.Table.from_pylist(december, schema=schema))
        table.refresh()
        third = table.current_snapshot()
        assert third is not None

        snapshots = list(table.snapshots())
        history = [
            {
                "snapshot_id": str(entry.snapshot_id),
                "operation": str(entry.summary.operation.value if entry.summary else "unknown"),
            }
            for entry in snapshots
        ]

        def value_at_snapshot(snapshot_id: int) -> str:
            frame = table.scan(snapshot_id=snapshot_id).to_arrow().to_pylist()
            found = [row for row in frame if row["period"] == PERIOD]
            return str(found[0]["value"]) if found else "absent"

        by_snapshot = {
            "load_1_june": value_at_snapshot(first.snapshot_id),
            "load_2_same_data_again": value_at_snapshot(second.snapshot_id),
            "load_3_december": value_at_snapshot(third.snapshot_id),
        }

        # WHAT AN OVERWRITE COSTS IN SNAPSHOTS IS A pyiceberg BEHAVIOUR AND NOT A LAW, and this
        # measures three shapes rather than generalising from one. The first version of this
        # exhibit asserted "an overwrite is two snapshots, a delete and an append" from the one
        # case above; a filtered overwrite, which is what an incremental loader actually writes,
        # produces a single OVERWRITE operation and no delete at all.
        variants: dict[str, list[str]] = {}

        def operations_of(table: Any) -> list[str]:
            return [
                str(entry.summary.operation.value if entry.summary else "unknown")
                for entry in table.snapshots()
            ]

        empty = catalog.create_table("ons.overwrite_empty", schema=schema)
        empty.overwrite(pa.Table.from_pylist(june, schema=schema))
        empty.refresh()
        variants["overwrite_of_an_empty_table"] = operations_of(empty)

        filtered = catalog.create_table("ons.overwrite_filtered", schema=schema)
        filtered.append(pa.Table.from_pylist(june, schema=schema))
        filtered.overwrite(
            pa.Table.from_pylist(
                [row for row in december if row["period"] == PERIOD], schema=schema
            ),
            # SPELLED WITH KEYWORDS ON PURPOSE. pyiceberg's own documentation writes this as
            # EqualTo("period", PERIOD) and that call is correct at runtime: LiteralPredicate
            # defines a real __init__ taking (term, literal) and coerces both. But EqualTo is
            # also a pydantic model, and what a type checker sees is the signature synthesised
            # from its FIELDS (type, term, value), under which the documented call has two
            # positional arguments too many. Measured: all three spellings build an identical
            # EqualTo(term=Reference('period'), literal=literal('2021')), and only this one
            # passes mypy --strict. Silencing the checker instead would have hidden the reason.
            overwrite_filter=EqualTo(term=Reference("period"), value=literal(PERIOD)),
        )
        filtered.refresh()
        variants["overwrite_with_a_filter"] = operations_of(filtered)
        variants["full_overwrite_twice"] = [entry["operation"] for entry in history]

        # THE OTHER DIRECTION, asked of the data rather than of the table's history.
        sys.path.insert(0, str(ROOT / "src"))
        from quarryz.stores import as_of

        with (VINTAGES / f"{SERIES}.csv").open(encoding="utf-8", newline="") as handle:
            triples = [
                (row["period"], row["value"], row["released"]) for row in csv.DictReader(handle)
            ]
        by_vintage = {
            "as_at_2023_06": (as_of(triples, PERIOD, BEFORE) or ("absent", ""))[0],
            "as_at_2023_12": (as_of(triples, PERIOD, AFTER) or ("absent", ""))[0],
        }

        # THE CHECK THAT THIS WENT OVER THE WIRE. A pyiceberg misconfiguration writing to the
        # local filesystem would otherwise produce a green run that proves nothing at all.
        listing = s3.list_objects_v2(Bucket=BUCKET)
        objects = int(listing.get("KeyCount", 0))
        if objects == 0:
            raise SystemExit(
                "the bucket is empty, so nothing reached S3 and this measured a local write"
            )
        stray = ROOT / "warehouse"
        if stray.exists():
            raise SystemExit(f"{stray} exists, so pyiceberg fell back to the local filesystem")

        summary = {
            "loads": 3,
            "snapshots": len(snapshots),
            "operations": [entry["operation"] for entry in history],
            "objects_in_s3": objects,
            "rows_june": len(june),
            "rows_december": len(december),
            "period": PERIOD,
            "overwrite_variants": variants,
            "by_snapshot": by_snapshot,
            "by_vintage": by_vintage,
        }

        if by_snapshot["load_1_june"] != by_snapshot["load_2_same_data_again"]:
            raise SystemExit(
                "loading the same data twice changed the value, which cannot be right and "
                "means the two loads were not the same corpus"
            )
        if by_snapshot["load_2_same_data_again"] == by_snapshot["load_3_december"]:
            raise SystemExit(
                "the December load did not change the value, so the revision is not in this "
                "corpus and the exhibit shows nothing"
            )

        (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

        with (OUT / "three-loads.txt").open("w", encoding="utf-8") as handle:
            print(
                f"$ python scripts/measure_snapshots.py   # {SERIES}, period {PERIOD}", file=handle
            )
            print(file=handle)
            print("--- three loads, and what the TABLE held after each ---", file=handle)
            print(
                f"load 1, the corpus as at {BEFORE}          {by_snapshot['load_1_june']}",
                file=handle,
            )
            print(
                f"load 2, THE SAME DATA AGAIN              "
                f" {by_snapshot['load_2_same_data_again']}",
                file=handle,
            )
            print(
                f"load 3, the corpus as at {AFTER}          {by_snapshot['load_3_december']}",
                file=handle,
            )
            print(file=handle)
            print(
                f"{len(snapshots)} snapshots for 3 loads: "
                f"{', '.join(entry['operation'] for entry in history)}",
                file=handle,
            )
            print(
                "An overwrite is two snapshots, a DELETE and an APPEND, so a retention rule",
                file=handle,
            )
            print("counting one snapshot per logical write is already wrong.", file=handle)
            print(file=handle)
            print(
                "--- the same question asked of the DATA rather than of the table ---", file=handle
            )
            print(
                f"what had the publisher said as at {BEFORE}   {by_vintage['as_at_2023_06']}",
                file=handle,
            )
            print(
                f"what had the publisher said as at {AFTER}   {by_vintage['as_at_2023_12']}",
                file=handle,
            )
            print(file=handle)
            print(
                "Load 2 moved the table's clock and moved no publisher's clock. A snapshot",
                file=handle,
            )
            print("records a load. Only the vintage records a publication.", file=handle)
            print(file=handle)
            print(f"--- and it really was S3: {objects} objects in the bucket ---", file=handle)
            # THE KEYS THEMSELVES ARE NOT PRINTED, and printing them made this transcript
            # unreproducible: pyiceberg names every data file with a fresh UUID, so each run
            # dirtied the working tree and the committed file could never match a CI run. The
            # shape is what a reader needs, and the shape is stable.
            shapes: dict[str, int] = {}
            for entry in listing.get("Contents", []):
                suffix = str(entry["Key"]).rsplit(".", 1)[-1]
                shapes[suffix] = shapes.get(suffix, 0) + 1
            for suffix, count in sorted(shapes.items()):
                print(f"  {count} .{suffix}", file=handle)
            print(
                "  (the file names carry a fresh UUID per run and are not recorded here)",
                file=handle,
            )

        print(json.dumps(summary, indent=2))
        return 0
    finally:
        server.terminate()
        server.wait(timeout=30)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
