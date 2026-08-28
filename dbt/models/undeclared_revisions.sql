{{ config(materialized="table") }}

-- The gate. A revision is acceptable when somebody declared the release that made it, AND the
-- number of periods it moved is the number they declared.
--
-- WHY THE LEDGER IS PER RELEASE AND NOT PER PERIOD. Six months of publication revised 445 of
-- IKBJ's 664 periods and 442 of DZLS's 516. A ledger with a row per revised period would need
-- over a thousand entries for one load, and a review nobody can perform is a review that gets
-- rubber stamped. So the unit is the release: "we accept that the 2023-10-11 release of IKBJ
-- rewrote history".
--
-- AND THE COUNT IS PART OF THE DECLARATION, which is what stops that from being a blanket
-- permission. Accepting a release accepts the SIZE of what it changed, so the same release
-- moving a different number of periods than was reviewed is undeclared again.

with counted as (
    select series, revised_at, count(*) as periods
    from {{ ref("revisions") }}
    group by series, revised_at
),

declared as (
    select series, released, periods_expected
    from read_csv('{{ var("ledger") }}', header = true, columns = {
        'series': 'VARCHAR', 'released': 'VARCHAR', 'periods_expected': 'INTEGER',
        'note': 'VARCHAR'
    })
)

select
    counted.series,
    counted.revised_at,
    counted.periods,
    declared.periods_expected,
    case
        when declared.series is null then 'no declaration for this release'
        when declared.periods_expected is null
            then 'declared with no count, which asserts nothing about what it moved'
        else 'declared ' || declared.periods_expected || ' periods and it moved ' || counted.periods
    end as why
from counted
left join declared
    on counted.series = declared.series
    and counted.revised_at = declared.released
-- `is null` ON THE COUNT AS WELL, and its absence was a hole big enough to drive the whole
-- gate through. With a blank cell the comparison `NULL != 445` evaluates to NULL rather than
-- TRUE, so the row was dropped and the build went green while the declaration asserted nothing.
-- Measured: a ledger declaring IKBJ 2023-10-11 with an empty count passed with PASS=7 while
-- that release moved 445 periods. Three-valued logic turns a missing value into a silent yes.
where declared.series is null
   or declared.periods_expected is null
   or declared.periods_expected != counted.periods
