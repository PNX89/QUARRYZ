#!/usr/bin/env bash
# The build that fails when a publisher rewrites history, run in both directions.
#
# Usage:  scripts/measure_gate.sh
#
# WHAT IS MEASURED. Six dbt builds against the committed corpus:
#
#   1. WITH THE LEDGER EMPTIED, which must FAIL. A gate that has never been seen to fail is a
#      gate nobody has tested, and this is the one claim the repository is named for.
#   2. WITH THE COMMITTED LEDGER, which must PASS. A gate that cannot be satisfied is a gate
#      that gets disabled on the second Monday.
#   3. WITH ONE DECLARATION'S COUNT BLANKED, which must FAIL. The gate's middle WHERE arm exists
#      because comparing a declared count against a blank cell gives NULL rather than TRUE, so
#      the row used to drop out and the build went green while the declaration asserted nothing.
#      Neither of the two builds above contains a blank count, so both produced identical output
#      with that arm present or deleted, and the only test naming the property was a substring
#      search over the model text that a SQL comment satisfies. An arm nothing reaches is an arm
#      nobody has tested.
#   4. OVER A WINDOW WHERE ONE DATE CARRIES TWO PUBLICATIONS, declared as one day, which must
#      FAIL. This is the gate's own unit under test: the model used to group on (series, date)
#      while the rest of the repository proved a date is not a key, so two rewrites on one
#      morning were reviewable as one.
#   5. OVER A DIFFERENT WINDOW, 2016 to 2017, which is where the withdrawal lives. The 2023
#      window contains 1,058 revisions and every one of them is a plain change, so the
#      withdrawn and restored branches would be dead code exercised by nothing.
#   6. AND OVER 2018 TO 2019, where the same periods come back.
#
# The ledger is emptied in a COPY under the target directory, never in the tree. A harness that
# edits committed files to prove a point leaves the repository dirty when it is interrupted.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/docs/evidence/gate"
DBT="$ROOT/dbt"
LEDGER="$ROOT/src/quarryz/data/declared_revisions.csv"

mkdir -p "$OUT"
cd "$DBT"

dbt_build() {
  uv run --group engines dbt build --profiles-dir . "$@" 2>&1
}

rows_in() {
  uv run --group engines python -c "
import duckdb, sys
con = duckdb.connect('target/quarryz.duckdb', read_only=True)
print(con.execute('select count(*) from ' + sys.argv[1]).fetchone()[0])
" "$1"
}

echo "==> 1. the ledger emptied, which must fail"
EMPTY="$DBT/target/empty_ledger"
mkdir -p "$EMPTY"
head -1 "$LEDGER" > "$EMPTY/declared_revisions.csv"
set +e
FAILED_OUTPUT="$(dbt_build --vars "{ledger: '$EMPTY/declared_revisions.csv'}")"
FAILED_CODE=$?
set -e
[ "$FAILED_CODE" -eq 0 ] && {
  echo "the build passed with an empty ledger, so the gate does not gate" >&2
  exit 1
}
# `|| true` on purpose: grep exits 1 when it matches nothing, and under `set -e` that would
# abort the run with no message rather than reporting that the failure looked wrong.
#
# AND `results?` WITH THE QUESTION MARK, because dbt writes "Got 1 result" and "Got 7 results".
# The plural-only pattern worked for as long as every measured failure happened to name more
# than one row, and the first single-row failure this harness measured aborted it.
UNDECLARED=$(printf '%s' "$FAILED_OUTPUT" | grep -oE "Got [0-9]+ results?" | grep -oE "[0-9]+" | head -1 || true)
[ -n "$UNDECLARED" ] || {
  echo "the build failed but not with a test result count, so the failure is not the one this" >&2
  echo "harness is measuring. The output was:" >&2
  printf '%s\n' "$FAILED_OUTPUT" | tail -20 >&2
  exit 1
}

echo "==> 2. the committed ledger, which must pass"
PASSED_OUTPUT="$(dbt_build)"
REVISIONS=$(rows_in revisions)
DECLARED=$(($(wc -l < "$LEDGER") - 1))

echo "==> 3. one declaration with its count blanked, which must fail"
# WHICH ROW IS CHOSEN IS COMPUTED, NOT NAMED. The largest declaration in the ledger is the one
# whose silent acceptance costs most, and naming a series here would leave this measuring
# nothing the day the ledger is rewritten. Everything but the count is left intact, so the
# failure can only come from the blank.
BLANK="$DBT/target/blank_count"
mkdir -p "$BLANK"
BLANKED=$(python3 - "$LEDGER" "$BLANK/declared_revisions.csv" <<'PYTHON'
import csv, json, sys

with open(sys.argv[1], encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
chosen = max(rows, key=lambda row: int(row["periods_expected"]))
moved = int(chosen["periods_expected"])
chosen["periods_expected"] = ""

with open(sys.argv[2], "w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

print(json.dumps({
    "series": chosen["series"],
    "released": chosen["released"],
    "version": chosen["version"],
    "periods_it_moved": moved,
}))
PYTHON
)
set +e
BLANK_OUTPUT="$(dbt_build --vars "{ledger: '$BLANK/declared_revisions.csv'}")"
BLANK_CODE=$?
set -e
[ "$BLANK_CODE" -eq 0 ] && {
  echo "a declaration with no count passed the gate, so a blank cell is a silent yes again" >&2
  exit 1
}
BLANK_UNDECLARED=$(printf '%s' "$BLANK_OUTPUT" | grep -oE "Got [0-9]+ results?" | grep -oE "[0-9]+" | head -1 || true)
[ -n "$BLANK_UNDECLARED" ] || {
  echo "the blank-count build failed without a test result count, so the failure is not the" >&2
  echo "one this harness is measuring. The output was:" >&2
  printf '%s\n' "$BLANK_OUTPUT" | tail -20 >&2
  exit 1
}

echo "==> 4. a morning carrying two publications, declared as one day, which must fail"
# THE GATE'S OWN UNIT, MEASURED. `revisions` is rebuilt over a window that contains a date on
# which the publisher issued twice, the two publications are read out of it, and a ledger
# declaring the DAY once with the day's total is offered to the full build. Under a date-keyed
# gate that ledger passes and one reviewer approves two rewrites; under this one neither
# publication is declared, which is the whole point of putting the version in the key.
SAME_DAY_WAREHOUSE="2015-12"
SAME_DAY_INCOMING="2016-02"
SAME_DAY_LEDGER="$DBT/target/same_day"
mkdir -p "$SAME_DAY_LEDGER"
dbt_build --select +revisions \
  --vars "{warehouse_as_at: '$SAME_DAY_WAREHOUSE', incoming_as_at: '$SAME_DAY_INCOMING'}" >/dev/null
SAME_DAY=$(uv run --group engines python - "$LEDGER" "$SAME_DAY_LEDGER/declared_revisions.csv" <<'PYTHON'
import csv, duckdb, json, sys

con = duckdb.connect("target/quarryz.duckdb", read_only=True)
groups = con.execute(
    "select series, revised_at, revised_by, count(*) from revisions "
    "group by 1, 2, 3 order by 1, 2, 3"
).fetchall()

shared = [
    (series, revised_at)
    for series, revised_at, _, _ in groups
    if sum(1 for other, when, _, _ in groups if (other, when) == (series, revised_at)) > 1
]
if not shared:
    raise SystemExit(
        "no date in this window carries two publications, so the window has to move rather "
        "than this measurement being dropped"
    )
series, released = shared[0]
publications = {version: periods for name, when, version, periods in groups
                if (name, when) == (series, released)}

with open(sys.argv[1], encoding="utf-8", newline="") as handle:
    fields = list(csv.DictReader(handle).fieldnames or [])
with open(sys.argv[2], "w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerow({
        "series": series,
        "released": released,
        "version": sorted(publications)[0],
        "periods_expected": sum(publications.values()),
        "note": "the whole morning declared as one release, which is what a date-keyed "
                "ledger can say and all it can say",
    })

print(json.dumps({
    "series": series,
    "released": released,
    "publications": publications,
}))
PYTHON
)
set +e
SAME_DAY_OUTPUT="$(dbt_build --vars "{warehouse_as_at: '$SAME_DAY_WAREHOUSE', incoming_as_at: '$SAME_DAY_INCOMING', ledger: '$SAME_DAY_LEDGER/declared_revisions.csv'}")"
SAME_DAY_CODE=$?
set -e
[ "$SAME_DAY_CODE" -eq 0 ] && {
  echo "declaring one morning as one release satisfied the gate, so two publications are" >&2
  echo "reviewable as one and the version is not in the key" >&2
  exit 1
}
SAME_DAY_UNDECLARED=$(printf '%s' "$SAME_DAY_OUTPUT" | grep -oE "Got [0-9]+ results?" | grep -oE "[0-9]+" | head -1 || true)
[ -n "$SAME_DAY_UNDECLARED" ] || {
  echo "the same-day build failed without a test result count, so the failure is not the one" >&2
  echo "this harness is measuring. The output was:" >&2
  printf '%s\n' "$SAME_DAY_OUTPUT" | tail -20 >&2
  exit 1
}

# TWO OLDER WINDOWS, ONE FOR EACH BRANCH, and the first attempt at this used ONE and got
# nothing. Asking 2017-06 against 2019-12 shows the 1997 periods as a plain `changed`, because
# by the end of that span they had been withdrawn AND restored and only the net difference
# survives a two-point comparison. A window is a pair of instants, not an interval, and an event
# that reverses inside it is invisible to it.
kinds_between() {
  # `+revisions`, WITH THE PLUS, and the first version of this did not have it. `--select
  # revisions` rebuilds that model alone and leaves its parents standing, so the cut-off
  # variables changed nothing at all: the model was rebuilt from a warehouse and an incoming
  # table still holding the 2023 window, and it faithfully reported the 2023 answer for a
  # question about 2017. A selector that quietly reuses upstream state is the same shape of
  # trap as a query returning yesterday's parts.
  dbt_build --select +revisions --vars "{warehouse_as_at: '$1', incoming_as_at: '$2'}" >/dev/null
  uv run --group engines python -c "
import duckdb, json
con = duckdb.connect('target/quarryz.duckdb', read_only=True)
# ORDER BY kind, AND THE VERSION WITHOUT IT MADE THIS FILE FLAKY. A bare group by returns its
# rows in whatever order the engine finds convenient, so two runs over identical data wrote the
# same two counts into summary.json in different orders. Nothing about the measurement changed
# and the JSON did, which means the CI step that diffs this file would have failed on some runs
# and passed on others: the worst kind of check, because the first response to it is to delete it.
print(json.dumps(dict(con.execute('select kind, count(*) from revisions group by kind order by kind').fetchall())))
"
}

echo "==> 5. 2016-12 to 2017-12, where a withdrawal lives"
WITHDRAWN_KINDS=$(kinds_between "2016-12" "2017-12")

echo "==> 6. 2018-06 to 2019-12, where the same periods come back"
RESTORED_KINDS=$(kinds_between "2018-06" "2019-12")
KINDS=$(python3 -c "
import json, sys
print(json.dumps({'withdrawal_window': json.loads(sys.argv[1]),
                  'restoration_window': json.loads(sys.argv[2])}))
" "$WITHDRAWN_KINDS" "$RESTORED_KINDS")

# Rebuild on the declared window so the database left behind matches the committed ledger.
dbt_build >/dev/null

# THE PER-SERIES SPLIT, COMPUTED RATHER THAN TYPED. The closing sentence of the transcript
# contrasts the series this window rewrote with the one it left alone, and it used to carry four
# numbers written by hand into a heredoc. A recapture could have moved every one of them while
# the sentence went on saying 445 and 887, which is the defect this repository is about, in its
# own evidence file.
PER_SERIES=$(uv run --group engines python -c "
import duckdb, json
con = duckdb.connect('target/quarryz.duckdb', read_only=True)
periods = dict(con.execute('select series, count(distinct period) from warehouse group by series').fetchall())
revised = dict(con.execute('select series, count(*) from revisions group by series').fetchall())
print(json.dumps({s: {'periods': periods[s], 'revised': revised.get(s, 0)} for s in sorted(periods)}))
")

python3 - "$OUT/summary.json" "$UNDECLARED" "$REVISIONS" "$DECLARED" "$KINDS" "$PER_SERIES" \
  "$BLANKED" "$BLANK_UNDECLARED" "$SAME_DAY" "$SAME_DAY_UNDECLARED" \
  "$SAME_DAY_WAREHOUSE" "$SAME_DAY_INCOMING" <<'PYTHON'
import json, sys

blanked = json.loads(sys.argv[7])
blanked["undeclared_publications"] = int(sys.argv[8])
same_day = json.loads(sys.argv[9])
same_day["undeclared_publications"] = int(sys.argv[10])
same_day["window"] = {"warehouse_as_at": sys.argv[11], "incoming_as_at": sys.argv[12]}

summary = {
    "undeclared_release_groups_when_ledger_emptied": int(sys.argv[2]),
    "revisions_in_the_declared_window": int(sys.argv[3]),
    "releases_declared_in_the_ledger": int(sys.argv[4]),
    "a_declaration_with_no_count": blanked,
    "one_morning_declared_as_one_release": same_day,
    "kinds_in_the_older_windows": json.loads(sys.argv[5]),
    "per_series_in_the_declared_window": json.loads(sys.argv[6]),
}

if summary["a_declaration_with_no_count"]["undeclared_publications"] == 0:
    print("blanking a count produced no undeclared publication, so the gate accepts a "
          "declaration that asserts nothing about what it moved", file=sys.stderr)
    raise SystemExit(1)
if len(summary["one_morning_declared_as_one_release"]["publications"]) < 2:
    print("the same-day window carries one publication, so it shows nothing about a date "
          "being the wrong unit and the window has to move", file=sys.stderr)
    raise SystemExit(1)
if summary["one_morning_declared_as_one_release"]["undeclared_publications"] == 0:
    print("declaring one morning as one release satisfied the gate, so the unit of declaration "
          "is the day again and two rewrites are reviewable as one", file=sys.stderr)
    raise SystemExit(1)

per_series = summary["per_series_in_the_declared_window"]
if not any(entry["revised"] == 0 for entry in per_series.values()):
    print("every series was revised in this window, so the contrast the transcript draws "
          "between a rewritten series and an untouched one has no example in it",
          file=sys.stderr)
    raise SystemExit(1)
if sum(entry["revised"] for entry in per_series.values()) != summary[
    "revisions_in_the_declared_window"
]:
    print("the per-series revision counts do not add up to the total, so one of the two is "
          "counting something else", file=sys.stderr)
    raise SystemExit(1)

if summary["undeclared_release_groups_when_ledger_emptied"] == 0:
    print("emptying the ledger produced no undeclared revisions, so the gate is not gating",
          file=sys.stderr)
    raise SystemExit(1)
if summary["revisions_in_the_declared_window"] == 0:
    print("the declared window contains no revisions at all, so the exhibit shows nothing",
          file=sys.stderr)
    raise SystemExit(1)
older = summary["kinds_in_the_older_windows"]
if "withdrawn" not in older["withdrawal_window"]:
    print("the withdrawal window contains no withdrawal, so that branch of the model is "
          "exercised by nothing and must not be claimed", file=sys.stderr)
    raise SystemExit(1)
if "restored" not in older["restoration_window"]:
    print("the restoration window contains no restoration, so a withdrawal here is "
          "indistinguishable from a series ending", file=sys.stderr)
    raise SystemExit(1)

with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(summary, handle, indent=2)
    handle.write("\n")
PYTHON

# THE TWO THINGS IN dbt's OUTPUT THAT CHANGE WHEN NOTHING CHANGES: the wall clock it stamps on
# every line, and the elapsed time in a test result. Both are removed here, and this is what
# makes the transcript something CI can `git diff --exit-code` rather than a file that is
# regenerated, differs, and is therefore never checked. Everything that carries meaning survives:
# the FAIL, the test name, the result count, the PASS= tally.
stabilise() {
  sed -E -e 's/\x1b\[[0-9;]*m//g' \
         -e 's/^[0-9]{2}:[0-9]{2}:[0-9]{2}  //' \
         -e 's/in [0-9]+\.[0-9]+s\]/in <elapsed>]/'
}

{
  echo "\$ dbt build   # with the ledger emptied"
  printf '%s\n' "$FAILED_OUTPUT" | grep -E "FAIL|ERROR|Got [0-9]+ results?|Done\." | stabilise
  echo
  echo "\$ dbt build   # with the committed ledger"
  printf '%s\n' "$PASSED_OUTPUT" | grep -E "PASS=|Completed successfully" | stabilise
  echo
  echo "\$ dbt build   # with one declaration's count blanked"
  printf '%s\n' "$BLANK_OUTPUT" | grep -E "FAIL|Got [0-9]+ results?|Done\." | stabilise
  echo
  echo "\$ dbt build   # one morning declared as one release, over $SAME_DAY_WAREHOUSE to $SAME_DAY_INCOMING"
  printf '%s\n' "$SAME_DAY_OUTPUT" | grep -E "FAIL|Got [0-9]+ results?|Done\." | stabilise
  python3 -c "
import json, sys
found = json.loads(sys.argv[1])
moved = ', '.join(f'{version} moving {periods} periods'
                  for version, periods in sorted(found['publications'].items()))
print(f\"  that morning is {found['series']} {found['released']}: {moved}\")
" "$SAME_DAY"
  echo
  echo "The $DECLARED publications the ledger declares, and what each moved:"
  tail -n +2 "$LEDGER" | cut -d, -f1-4 | sed 's/^/  /'
  echo
  echo "What those six months of publication did to each series:"
  python3 -c "
import json, sys
for series, entry in json.loads(sys.argv[1]).items():
    print(f\"  {series}  {entry['revised']:>4} of {entry['periods']} periods revised\")
" "$PER_SERIES"
  echo
  echo "A gate that fires per load rather than per series would have blocked the untouched one"
  echo "on another publisher's rewrite, which is how a gate ends up switched off."
} > "$OUT/both-directions.txt"

echo
echo "==> written to docs/evidence/gate:"
ls -1 "$OUT"
echo
cat "$OUT/summary.json"
