#!/usr/bin/env bash
# The build that fails when a publisher rewrites history, run in both directions.
#
# Usage:  scripts/measure_gate.sh
#
# WHAT IS MEASURED. Three dbt builds against the committed corpus:
#
#   1. WITH THE LEDGER EMPTIED, which must FAIL. A gate that has never been seen to fail is a
#      gate nobody has tested, and this is the one claim the repository is named for.
#   2. WITH THE COMMITTED LEDGER, which must PASS. A gate that cannot be satisfied is a gate
#      that gets disabled on the second Monday.
#   3. OVER A DIFFERENT WINDOW, 2017 to 2019, which is where the withdrawal lives. The 2023
#      window contains 1,058 revisions and every one of them is a plain change, so the
#      withdrawn and restored branches would be dead code exercised by nothing.
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
UNDECLARED=$(printf '%s' "$FAILED_OUTPUT" | grep -oE "Got [0-9]+ results" | grep -oE "[0-9]+" | head -1 || true)
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
print(json.dumps(dict(con.execute('select kind, count(*) from revisions group by kind').fetchall())))
"
}

echo "==> 3. 2016-12 to 2017-12, where a withdrawal lives"
WITHDRAWN_KINDS=$(kinds_between "2016-12" "2017-12")

echo "==> 4. 2018-06 to 2019-12, where the same periods come back"
RESTORED_KINDS=$(kinds_between "2018-06" "2019-12")
KINDS=$(python3 -c "
import json, sys
print(json.dumps({'withdrawal_window': json.loads(sys.argv[1]),
                  'restoration_window': json.loads(sys.argv[2])}))
" "$WITHDRAWN_KINDS" "$RESTORED_KINDS")

# Rebuild on the declared window so the database left behind matches the committed ledger.
dbt_build >/dev/null

python3 - "$OUT/summary.json" "$UNDECLARED" "$REVISIONS" "$DECLARED" "$KINDS" <<'PYTHON'
import json, sys

summary = {
    "undeclared_release_groups_when_ledger_emptied": int(sys.argv[2]),
    "revisions_in_the_declared_window": int(sys.argv[3]),
    "releases_declared_in_the_ledger": int(sys.argv[4]),
    "kinds_in_the_older_windows": json.loads(sys.argv[5]),
}

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

{
  echo "\$ dbt build   # with the ledger emptied"
  printf '%s\n' "$FAILED_OUTPUT" | grep -E "FAIL|ERROR|Got [0-9]+ results|Done\." | sed 's/\x1b\[[0-9;]*m//g'
  echo
  echo "\$ dbt build   # with the committed ledger"
  printf '%s\n' "$PASSED_OUTPUT" | grep -E "PASS=|Completed successfully" | sed 's/\x1b\[[0-9;]*m//g'
  echo
  echo "The seven releases the ledger declares, and what each moved:"
  tail -n +2 "$LEDGER" | cut -d, -f1-3 | sed 's/^/  /'
  echo
  echo "And MGRZ is in none of them. The same six months of publication revised 445 of IKBJ's"
  echo "664 periods and 0 of MGRZ's 887, so a gate that fires per load rather than per series"
  echo "would have blocked a clean series on another publisher's rewrite."
} > "$OUT/both-directions.txt"

echo
echo "==> written to docs/evidence/gate:"
ls -1 "$OUT"
echo
cat "$OUT/summary.json"
