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
# STDIN IS CLOSED FOR EVERY QUERY, and leaving it open is a hang rather than an error.
# `clickhouse local --query "INSERT ... VALUES (...)"` goes on reading stdin for further rows
# after the inline ones, so the harness ran fine in CI, where stdin is already closed, and hung
# on the first insert when run from an interactive shell. A script that behaves differently
# depending on who called it is a script that works until somebody debugs it.
ch() { "$CH" local --path "$WORK/db" --query "$1" < /dev/null; }

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

echo "==> the design this repository called the cure, on two versions published the same day"
# REAL VALUES FROM THE COMMITTED CORPUS, not a fixture. IKBJ period "2015 APR" was published
# twice on 2016-01-08, as v3 at -2548 and v4 at -2584, and both are in
# src/quarryz/data/vintages/IKBJ.csv. A fixture would have let me choose two different dates and
# never find this.
ch "CREATE TABLE by_date (
      series String, period String, value Float64, vintage Date
    ) ENGINE = ReplacingMergeTree
    ORDER BY (series, period, vintage)"
ch "INSERT INTO by_date VALUES
      ('IKBJ', '2015 APR', -2548, '2016-01-08'),
      ('IKBJ', '2015 APR', -2584, '2016-01-08')"
BY_DATE_BEFORE=$(ch "SELECT count() FROM by_date")
ch "OPTIMIZE TABLE by_date FINAL" >/dev/null
BY_DATE_AFTER=$(ch "SELECT count() FROM by_date")
BY_DATE_SURVIVOR=$(ch "SELECT toString(value) FROM by_date")

echo "==> and the design that actually keeps them: the version in the key as well"
ch "CREATE TABLE by_pair (
      series String, period String, value Float64, vintage Date, version String
    ) ENGINE = ReplacingMergeTree
    ORDER BY (series, period, vintage, version)"
ch "INSERT INTO by_pair VALUES
      ('IKBJ', '2015 APR', -2548, '2016-01-08', 'v3'),
      ('IKBJ', '2015 APR', -2584, '2016-01-08', 'v4')"
ch "OPTIMIZE TABLE by_pair FINAL" >/dev/null
BY_PAIR=$(ch "SELECT count() FROM by_pair")
# The as-of projection over a TOTAL ordering key. argMax over the date alone has no defined
# answer when two rows share the largest key, which is the same defect one level up.
AS_OF_V3=$(ch "SELECT toString(argMax(value, (vintage, version))) FROM by_pair
                WHERE version <= 'v3'")
AS_OF_V4=$(ch "SELECT toString(argMax(value, (vintage, version))) FROM by_pair")

# THE WHOLE CORPUS THROUGH BOTH DESIGNS, because two rows prove the mechanism and the corpus
# says what it costs.
CORPUS="$WORK/corpus.csv"
: > "$CORPUS"
for name in IKBJ DZLS KAC3 MGRZ; do
  tail -n +2 "$ROOT/src/quarryz/data/vintages/$name.csv" |
    awk -F, -v s="$name" '{print s "," $1 "," $2 "," $3 "," $4}' >> "$CORPUS"
done
ch "CREATE TABLE corpus (
      series String, period String, value String, released String, version String
    ) ENGINE = MergeTree ORDER BY (series, period, released, version)"
"$CH" local --path "$WORK/db" --query "INSERT INTO corpus FORMAT CSV" < "$CORPUS"
CORPUS_ROWS=$(ch "SELECT count() FROM corpus")
KEPT_BY_PAIR=$(ch "SELECT uniqExact((series, period, released, version)) FROM corpus")
KEPT_BY_DATE=$(ch "SELECT uniqExact((series, period, released)) FROM corpus")
DESTROYED=$((CORPUS_ROWS - KEPT_BY_DATE))

{
  echo "\$ clickhouse local, two versions the publisher released on the SAME DAY"
  echo "# IKBJ '2015 APR', both released 2016-01-08: v3 at -2548 and v4 at -2584."
  echo "# Real rows from src/quarryz/data/vintages/IKBJ.csv, not a fixture."
  echo
  echo "--- ORDER BY (series, period, vintage), which this repository called the cure ---"
  echo "SELECT count() FROM by_date            -> $BY_DATE_BEFORE"
  echo "after OPTIMIZE TABLE by_date FINAL     -> $BY_DATE_AFTER"
  echo "the value still readable               -> $BY_DATE_SURVIVOR"
  echo
  echo "That is the SAME behaviour as the naive table above. A vintage stored as a DATE is not"
  echo "a unique key, this repository documents that fact in four other places, and the design"
  echo "offered as the fix repeated the defect."
  echo
  echo "--- ORDER BY (series, period, vintage, version) ---"
  echo "SELECT count() FROM by_pair            -> $BY_PAIR"
  echo "argMax(value, (vintage, version)) at v3 -> $AS_OF_V3"
  echo "argMax(value, (vintage, version)) at v4 -> $AS_OF_V4"
  echo
  echo "--- and the whole committed corpus through both ---"
  echo "rows loaded                            -> $CORPUS_ROWS"
  echo "surviving a (series, period, released, version) key -> $KEPT_BY_PAIR"
  echo "surviving a (series, period, released) key          -> $KEPT_BY_DATE"
  echo "published values a date-only key destroys           -> $DESTROYED"
} > "$OUT/the-vintage-in-the-key.txt"

export BEFORE_PLAIN AFTER_PLAIN BEFORE_FINAL AFTER_FINAL SURVIVOR ONE_INSERT_ROWS \
  ONE_INSERT_PARTS BY_DATE_BEFORE BY_DATE_AFTER BY_DATE_SURVIVOR BY_PAIR AS_OF_V3 AS_OF_V4 \
  CORPUS_ROWS KEPT_BY_PAIR KEPT_BY_DATE DESTROYED

python3 - "$OUT/summary.json" <<'PYTHON'
import json, os, sys

def number(name):
    return int(os.environ[name])

summary = {
    "naive_key": {
        "rows_before_merge": number("BEFORE_PLAIN"),
        "rows_after_optimize": number("AFTER_PLAIN"),
        "rows_final_before": number("BEFORE_FINAL"),
        "rows_final_after": number("AFTER_FINAL"),
        "surviving_vintage": os.environ["SURVIVOR"].strip(),
    },
    "one_insert": {
        "rows": number("ONE_INSERT_ROWS"),
        "active_parts": number("ONE_INSERT_PARTS"),
    },
    "vintage_as_a_date": {
        "rows_before_merge": number("BY_DATE_BEFORE"),
        "rows_after_optimize": number("BY_DATE_AFTER"),
        "surviving_value": os.environ["BY_DATE_SURVIVOR"].strip(),
    },
    "vintage_and_version": {
        "rows": number("BY_PAIR"),
        "as_of_v3": os.environ["AS_OF_V3"].strip(),
        "as_of_v4": os.environ["AS_OF_V4"].strip(),
    },
    "whole_corpus": {
        "rows": number("CORPUS_ROWS"),
        "kept_by_a_pair_key": number("KEPT_BY_PAIR"),
        "kept_by_a_date_key": number("KEPT_BY_DATE"),
        "destroyed_by_a_date_key": number("DESTROYED"),
    },
}

if summary["naive_key"]["rows_before_merge"] == summary["naive_key"]["rows_after_optimize"]:
    print("the naive table did not collapse, so this repository's first exhibit is not "
          "reproducible on this ClickHouse. Read the transcripts before changing the claim.",
          file=sys.stderr)
    raise SystemExit(1)
if summary["vintage_as_a_date"]["rows_after_optimize"] != 1:
    print("two versions released on the same day survived a date-only sort key, so the second "
          "exhibit no longer holds and the correction it records may be unnecessary",
          file=sys.stderr)
    raise SystemExit(1)
if summary["vintage_and_version"]["rows"] != 2:
    print("the pair key did not keep both versions, which is the design this repository now "
          "recommends and it must not be recommended unmeasured", file=sys.stderr)
    raise SystemExit(1)
if summary["whole_corpus"]["destroyed_by_a_date_key"] <= 0:
    print("a date-only key destroys nothing in this corpus, so the correction has no cost to "
          "quote and the claim must be dropped rather than asserted", file=sys.stderr)
    raise SystemExit(1)
if summary["whole_corpus"]["kept_by_a_pair_key"] != summary["whole_corpus"]["rows"]:
    print("the pair key loses rows too, which would mean the corpus contains two identical "
          "keys and the capture is wrong rather than the engine", file=sys.stderr)
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
