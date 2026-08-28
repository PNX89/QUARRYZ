#!/usr/bin/env bash
# What each storage choice does to a publisher's earlier vintages, measured rather than argued.
#
# Usage:  scripts/measure_collapse.sh
#
# THE QUESTION. A revisable number arrives more than once: the publisher says 100.0 in March and
# 105.5 in May for the same period. A warehouse has to decide what to keep, and the obvious
# ClickHouse answer, a ReplacingMergeTree keyed on the observation, is the one this measures
# first, because it is what a person reaches for when they want the latest value per key and it
# is wrong here in a way that leaves no trace.
#
# WHAT IS RECORDED AND WHAT IS NOT. summary.json carries the counts, which are decided by the
# engine's rules and are the same everywhere. The transcripts carry the queries and their output
# for a reader. Part names and merge timings are NOT recorded, because they vary between runs
# and a diff over them would fail for reasons nobody cares about.
#
# THE WORD "NONDETERMINISTIC" IS NOT USED ANYWHERE HERE, and that is deliberate. Six identical
# runs during the pre-flight produced six identical results, so a reviewer who tests that word
# will find it reproducible and will be right to complain. What is true is narrower and worse:
# the answer is a function of merge scheduling and of how much unrelated data has arrived, not
# of the data being queried or of the query. It is reproducible and it is not controllable.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/docs/evidence/collapse"
CH="$ROOT/bin/clickhouse"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

[ -x "$CH" ] || { echo "bin/clickhouse is missing. Run scripts/fetch_tools.sh" >&2; exit 1; }
mkdir -p "$OUT"

# One invocation per query so each starts from the state left on disk, which is the point: a
# single session would keep everything in one process and hide the part lifecycle entirely.
ch() { "$CH" local --path "$WORK/db" --query "$1"; }

echo "==> the design a person reaches for: ReplacingMergeTree keyed on the observation"
ch "CREATE TABLE naive (
      series String, period Date, value Float64, vintage Date
    ) ENGINE = ReplacingMergeTree(vintage)
    ORDER BY (series, period)"

# SEPARATE INSERTS, so each lands in its own part and nothing is collapsed at write time. That
# distinction is measured on its own below.
ch "INSERT INTO naive VALUES ('GDP', '2020-04-01', 100.0, '2020-08-11')"
ch "INSERT INTO naive VALUES ('GDP', '2020-04-01', 105.5, '2021-02-12')"

BEFORE_PLAIN=$(ch "SELECT count() FROM naive")
BEFORE_FINAL=$(ch "SELECT count() FROM naive FINAL")
ch "OPTIMIZE TABLE naive FINAL" >/dev/null
AFTER_PLAIN=$(ch "SELECT count() FROM naive")
AFTER_FINAL=$(ch "SELECT count() FROM naive FINAL")
SURVIVOR=$(ch "SELECT toString(vintage) FROM naive FINAL")

{
  echo "\$ clickhouse local, ReplacingMergeTree(vintage) ORDER BY (series, period)"
  echo "# two vintages of one observation, inserted separately"
  echo
  echo "--- before any merge ---"
  echo "SELECT count() FROM naive          -> $BEFORE_PLAIN"
  echo "SELECT count() FROM naive FINAL    -> $BEFORE_FINAL"
  echo
  echo "--- after OPTIMIZE TABLE naive FINAL ---"
  echo "SELECT count() FROM naive          -> $AFTER_PLAIN"
  echo "SELECT count() FROM naive FINAL    -> $AFTER_FINAL"
  echo
  echo "The same unchanged query returned $BEFORE_PLAIN rows and then $AFTER_PLAIN."
  echo "The vintage still readable is $SURVIVOR, and the other one is not readable by any query."
} > "$OUT/the-obvious-design.txt"

echo "==> the same two vintages in ONE insert"
ch "CREATE TABLE one_insert (
      series String, period Date, value Float64, vintage Date
    ) ENGINE = ReplacingMergeTree(vintage)
    ORDER BY (series, period)"
ch "INSERT INTO one_insert VALUES
      ('GDP', '2020-04-01', 100.0, '2020-08-11'),
      ('GDP', '2020-04-01', 105.5, '2021-02-12')"
ONE_INSERT_ROWS=$(ch "SELECT count() FROM one_insert")
ONE_INSERT_PARTS=$(ch "SELECT count() FROM system.parts
                       WHERE table = 'one_insert' AND active")

{
  echo "\$ clickhouse local, the same table, both vintages in a single INSERT"
  echo
  echo "SELECT count() FROM one_insert                     -> $ONE_INSERT_ROWS"
  echo "SELECT count() FROM system.parts WHERE active      -> $ONE_INSERT_PARTS"
  echo
  echo "One part, and no merge has run. The earlier vintage was never written to disk, so"
  echo "there is no moment at which a check could have caught it and nothing to optimise away."
} > "$OUT/one-insert.txt"

echo "==> and the design that keeps them: the vintage in the sort key"
ch "CREATE TABLE bitemporal (
      series String, period Date, value Float64, vintage Date
    ) ENGINE = ReplacingMergeTree
    ORDER BY (series, period, vintage)"
ch "INSERT INTO bitemporal VALUES
      ('GDP', '2020-04-01', 100.0, '2020-08-11'),
      ('GDP', '2020-04-01', 105.5, '2021-02-12')"
ch "OPTIMIZE TABLE bitemporal FINAL" >/dev/null
KEPT_PLAIN=$(ch "SELECT count() FROM bitemporal")
KEPT_FINAL=$(ch "SELECT count() FROM bitemporal FINAL")
# The as-of projection: what the publisher said about this period as at a date.
AS_OF_2020=$(ch "SELECT toString(argMax(value, vintage)) FROM bitemporal
                 WHERE series = 'GDP' AND period = '2020-04-01' AND vintage <= '2020-12-31'")
AS_OF_2021=$(ch "SELECT toString(argMax(value, vintage)) FROM bitemporal
                 WHERE series = 'GDP' AND period = '2020-04-01' AND vintage <= '2021-12-31'")

{
  echo "\$ clickhouse local, ReplacingMergeTree ORDER BY (series, period, vintage)"
  echo "# the same two vintages, in one INSERT, and OPTIMIZE TABLE ... FINAL run deliberately"
  echo
  echo "SELECT count() FROM bitemporal        -> $KEPT_PLAIN"
  echo "SELECT count() FROM bitemporal FINAL  -> $KEPT_FINAL"
  echo
  echo "--- the as-of projection, which is what the collapsing table was trying to give ---"
  echo "argMax(value, vintage) WHERE vintage <= 2020-12-31  -> $AS_OF_2020"
  echo "argMax(value, vintage) WHERE vintage <= 2021-12-31  -> $AS_OF_2021"
  echo
  echo "Two different answers to the same question asked at two moments, which is the thing"
  echo "the first table cannot do at all once it has collapsed."
} > "$OUT/the-vintage-in-the-key.txt"

python3 - "$OUT/summary.json" <<PYTHON
import json, sys

summary = {
    "naive_key": {
        "rows_before_merge": $BEFORE_PLAIN,
        "rows_after_optimize": $AFTER_PLAIN,
        "rows_final_before": $BEFORE_FINAL,
        "rows_final_after": $AFTER_FINAL,
        "surviving_vintage": "$SURVIVOR",
    },
    "one_insert": {
        "rows": $ONE_INSERT_ROWS,
        "active_parts": $ONE_INSERT_PARTS,
    },
    "vintage_in_key": {
        "rows": $KEPT_PLAIN,
        "rows_final": $KEPT_FINAL,
        "as_of_2020": $AS_OF_2020,
        "as_of_2021": $AS_OF_2021,
    },
}

# A run that measured nothing must not write a summary that reads like one.
if summary["naive_key"]["rows_before_merge"] == summary["naive_key"]["rows_after_optimize"]:
    print("the naive table did not collapse, so this repository's first exhibit is not "
          "reproducible on this ClickHouse. Read the transcripts before changing the claim.",
          file=sys.stderr)
    raise SystemExit(1)
if summary["vintage_in_key"]["as_of_2020"] == summary["vintage_in_key"]["as_of_2021"]:
    print("the two as-of answers are the same, so the fixture has no revision in it and the "
          "comparison shows nothing", file=sys.stderr)
    raise SystemExit(1)

with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(summary, handle, indent=2)
    handle.write("\n")
PYTHON

echo
echo "==> written to docs/evidence/collapse:"
ls -1 "$OUT"
echo
cat "$OUT/summary.json"
