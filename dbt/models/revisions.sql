{{ config(materialized="table") }}

-- What the incoming load CHANGES about periods the warehouse already holds.
--
-- A REVISION IS NOT A NEW PERIOD, and conflating the two is the mistake that makes a revision
-- gate useless. Every load adds periods, because time passes and the publisher publishes; a
-- gate that fires on those fires on every load and is switched off within a week. What is
-- caught here is a period we ALREADY HAD whose value the publisher has since changed.
--
-- A period that DISAPPEARS is not covered by this model either. It is a third event, and the
-- test beside it asserts that none has happened in this corpus rather than leaving the silence
-- to be read as coverage.

select
    incoming.series,
    incoming.period,
    warehouse.value as was,
    incoming.value as now,
    warehouse.released as recorded_at,
    incoming.released as revised_at,
    incoming.version as revised_by,
    case
        when warehouse.value = 'WITHDRAWN' then 'restored'
        when incoming.value = 'WITHDRAWN' then 'withdrawn'
        else 'changed'
    end as kind
from {{ ref("incoming") }} as incoming
inner join {{ ref("warehouse") }} as warehouse
    on incoming.series = warehouse.series
    and incoming.period = warehouse.period
where incoming.value is distinct from warehouse.value
