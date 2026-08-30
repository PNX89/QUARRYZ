{{ config(materialized="table") }}

-- The gate. A revision is acceptable when somebody declared the PUBLICATION that made it, AND
-- the number of periods it moved is the number they declared.
--
-- WHY THE LEDGER IS PER PUBLICATION AND NOT PER PERIOD. Six months of publication revised 445 of
-- IKBJ's 664 periods and 442 of DZLS's 516. A ledger with a row per revised period would need
-- over a thousand entries for one load, and a review nobody can perform is a review that gets
-- rubber stamped. So the unit is the publication: "we accept that IKBJ v111, released
-- 2023-10-11, rewrote history".
--
-- AND THE UNIT IS THE PUBLICATION AND NOT THE DAY, which this model got wrong while the rest of
-- the repository spent its README proving that a release date is not a key. `counted` grouped on
-- (series, revised_at) and the ledger had no version column, so two publications on one morning
-- became one group with one count and a reviewer approving that row approved two separate
-- rewrites as one. Twelve series-and-date pairs in this corpus carry two versions, and the gate
-- meets them: over 2015-12 to 2016-02, IKBJ's 2016-01-08 is v3 moving 16 periods and v4 moving
-- 14, which a date-shaped ledger declares as one release of 30. That is the same defect the
-- collapse exhibit measures in ClickHouse, on the same date, in the model that exists to catch
-- it. `revisions` already carried `revised_by`; this model threw it away.
--
-- AND THE COUNT IS PART OF THE DECLARATION, which is what stops that from being a blanket
-- permission. Accepting a publication accepts the SIZE of what it changed, so the same
-- publication moving a different number of periods than was reviewed is undeclared again.

with counted as (
    select series, revised_at, revised_by, count(*) as periods
    from {{ ref("revisions") }}
    group by series, revised_at, revised_by
),

declared as (
    select series, released, version, periods_expected
    from read_csv('{{ var("ledger") }}', header = true, columns = {
        'series': 'VARCHAR', 'released': 'VARCHAR', 'version': 'VARCHAR',
        'periods_expected': 'INTEGER', 'note': 'VARCHAR'
    })
)

select
    counted.series,
    counted.revised_at,
    counted.revised_by,
    counted.periods,
    declared.periods_expected,
    case
        when declared.series is null then 'no declaration for this publication'
        when declared.periods_expected is null
            then 'declared with no count, which asserts nothing about what it moved'
        else 'declared ' || declared.periods_expected || ' periods and it moved ' || counted.periods
    end as why
from counted
left join declared
    on counted.series = declared.series
    and counted.revised_at = declared.released
    and counted.revised_by = declared.version
-- `is null` ON THE COUNT AS WELL, and its absence was a hole big enough to drive the whole
-- gate through. With a blank cell the comparison evaluates to NULL rather than TRUE, so the row
-- was dropped and the build went green while the declaration asserted nothing. Three-valued
-- logic turns a missing value into a silent yes.
--
-- AND NOW SOMETHING REACHES IT. Nothing did: the harness built with the ledger emptied and with
-- the ledger intact, and neither contains a blank count, so both runs produced identical output
-- whether this line was here or deleted. scripts/measure_gate.sh now builds a third time with
-- the ledger's largest declaration stripped of its count and requires that build to fail, and
-- the outcome is recorded in docs/evidence/gate for the offline suite to assert.
where declared.series is null
   or declared.periods_expected is null
   or declared.periods_expected != counted.periods
