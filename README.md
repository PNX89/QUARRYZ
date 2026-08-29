# QUARRYZ

**A statistical office revises the past. This is the warehouse that keeps every version of it,
and the build that fails when a revision arrives undeclared instead of quietly rewriting last
quarter's research.**

[![CI](https://github.com/PNX89/QUARRYZ/actions/workflows/ci.yml/badge.svg)](https://github.com/PNX89/QUARRYZ/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Three clocks run through any warehouse holding official statistics, and two of them are
routinely mistaken for each other.

| Clock | What it records | Where it comes from |
|---|---|---|
| **Valid time** | the period the number is about | the publisher |
| **Transaction time** | when the publisher said it | the publisher |
| **Snapshot time** | when we loaded it | us |

A snapshot records that **we** changed the table. A vintage records that the **publisher**
changed the number. Answering a question about the second by reading the first gives you an
answer, and it is about the wrong thing.

One file to start with: [`src/quarryz/stores.py`](src/quarryz/stores.py). It names the clocks,
and every claim it makes about a storage design is joined to a measurement under
[`docs/evidence/`](docs/evidence).

## What a key throws away, measured on 23,943 published values

The four series in this repository carry 23,943 recorded changes across 535 published versions.
Loading them into a ReplacingMergeTree, which is the ordinary way to hold a table that gets
restated, gives four different answers depending on one line of DDL.

| Key | Rows kept | What it costs |
|---|---|---|
| `(series, period)` | 1 | every version but the last |
| `(series, period)`, both rows in one insert | 1 | the earlier version never reaches disk |
| `(series, period, vintage)` where `vintage` is a `Date` | 23,872 | **71 published values, silently** |
| `(series, period, vintage, version)` | 23,943 | nothing |

The third row is the one worth pausing on, because it was this repository's own recommendation.
A vintage stored as a date looks like a total order and is not one: the publisher can issue two
versions on the same morning, and this corpus contains dates where it did. Under that key the
second overwrites the first, `OPTIMIZE FINAL` makes it permanent, and nothing anywhere reports
a loss. The measurement is in [`docs/evidence/collapse/`](docs/evidence/collapse), and the wrong
design is kept there beside the right one rather than deleted.

## The build that fails when the publisher rewrites history

The gate is a dbt test. A load that changes a value for a period the warehouse already holds
must be declared in a ledger, and an undeclared change fails the build:

<!-- quoted from docs/evidence/gate/both-directions.txt -->
```text
$ dbt build   # with the ledger emptied
[ERROR]: in test assert_every_revision_was_declared (tests/assert_every_revision_was_declared.sql)
  Got 7 results, configured to fail if != 0
```

Emptying the ledger produces 7 undeclared release groups, and that failure is measured on every
CI run rather than described. So is the other direction: with the committed ledger declaring
1,058 revised periods across 7 releases, the same build passes. A gate nobody has watched fail
is a gate nobody has tested, and a gate that cannot be satisfied is one that gets switched off.

**A new period is not a revision.** Every load adds periods, because time passes. A gate firing
on those fires on every load and is gone within a week, so the model joins only on periods the
warehouse already holds.

**And the gate fires per series, not per load.** The same six months of publication rewrote
three of these four series and left MGRZ untouched across all 887 of its periods. A gate keyed
on the load would have blocked a clean series because a different publisher restated something.

## Same definition, three engines, and the tie that decides it

The as-of question is written three ways, because the engines do not share an idiom:

<!-- quoted from docs/evidence/agreement/one-question.txt -->
```text
clickhouse  argMax(value, (released, version))
duckdb      row_number() over (order by released desc, version desc)
postgres    distinct on (period) ... order by released desc, version desc
```

All three are run against the same corpus and every period is compared. At the later moment
they agree on all 667 periods. That agreement is worth very little on its own, because it was
asked where nothing could go wrong.

The value is in the second moment. This series has release dates carrying two versions with
different values, and `argMax(value, released)` has **no defined answer** at a tie. Asked at a
cut-off where later releases have superseded every tied period, the wrong query returns the
right answer for all of them. Asked at 2016-01, it returns the superseded value for 14 periods.
That query was in this repository, and the check that passed it only ever asked the easy
question.

## A snapshot records a load, not a publication

Three loads into an Apache Iceberg table on a real S3 endpoint produce 5 snapshots. The second
load is the same data again: it moves the table's clock and no publisher's clock at all.

Asked what it held after the December load, the table gives the revised figure. Asked what the
publisher had said by December, the corpus gives the same. They agree there, and the second load
is where they come apart.

How many snapshots a write costs is a property of the call rather than of the load. An overwrite
of an empty table is one append; an overwrite with a filter is an append, an overwrite and an
append; a full overwrite of a populated table is a delete and an append. A retention rule
counting deletes would have been wrong about the commonest of the three.

## The corpus, and what the publisher actually did to it

703 kB of real Office for National Statistics data, captured by walking each series back through
its published versions until the archive returns a 404: 4 series, 535 versions, 23,943 changes.
It is committed rather than fetched, so every measurement here runs offline and reproduces.

The four were chosen because each carries a trap:

- a period published twice on one day with two different values
- a period withdrawn and later restored, which a single window cannot see
- a series renamed without a single number moving
- the largest single revision in the set, IKBJ's 2021 balance, restated from **-28,039** to
  **-3,518**: a move of **24,521** million pounds in one release

Licensed under the Open Government Licence v3.0, whose permissions include adapting the
information. [`SOURCE.json`](src/quarryz/data/vintages/SOURCE.json) records what was captured
and when, and the tests recompute every figure in it that a CSV of numbers can support.

## Run it

The offline suite needs nothing but Python. It reads committed JSON and CSV, and it is what a
stranger gets by cloning this:

```text
uv run pytest
```

The measurements are separate, because each needs an engine:

```text
scripts/fetch_tools.sh
scripts/measure_collapse.sh
scripts/measure_gate.sh
uv run --group engines python scripts/measure_snapshots.py
uv run --group engines python scripts/measure_agreement.py
```

Each rewrites its own directory under `docs/evidence`, and CI runs all five and fails if a
single byte of the result changed. The transcripts are diffed as well as the summaries, which
meant stripping the wall clock dbt prints on every line before any of it could be compared.

## What this does not do

It does not answer questions for anybody. It stores versions, detects undeclared revisions and
compares engines, and the as-of query here exists to be checked rather than to be served.

It does not detect a period that simply disappears. The capture emits a row when a value
changes, and a dropped period emits nothing, so the corpus cannot represent the event. There
was a dbt test asserting no period ever vanishes, and it could not fail: the warehouse and the
incoming load are two prefix bounds on one table, so the anti-join is empty by construction. It
was deleted and the limitation written down instead.

It measures four series from one publisher. Nothing here establishes how another statistical
office behaves, and the European Central Bank was examined and ruled out for this purpose: its
reuse policy permits redistribution only without modification, including of the metadata.

## Development

```text
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy src tests scripts
```

## Licence

MIT for the code. The statistics are Crown copyright, reproduced under the Open Government
Licence v3.0 and attributed in [`SOURCE.json`](src/quarryz/data/vintages/SOURCE.json).
