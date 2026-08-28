{{ config(materialized="table") }}

-- What the incoming load CHANGES about periods the warehouse already holds.
--
-- A REVISION IS NOT A NEW PERIOD, and conflating the two is the mistake that makes a revision
-- gate useless. Every load adds periods, because time passes and the publisher publishes; a
-- gate that fires on those fires on every load and is switched off within a week. What is
-- caught here is a period we ALREADY HAD whose value the publisher has since changed.
--
-- A PERIOD THAT DISAPPEARS IS NOT DETECTED HERE, AND THIS REPOSITORY DOES NOT CLAIM TO DETECT
-- ONE. There used to be a dbt test beside this model asserting that none ever had, and it was
-- worse than nothing twice over.
--
-- It could not fail. `warehouse` and `incoming` are the same table filtered by
-- `substr(released, 1, N) <= cut_off`, so whenever the warehouse cut-off is the earlier of the
-- two, every row qualifying for the warehouse also qualifies for the incoming load and the
-- anti-join is empty by construction. Only an inverted window makes it fire, and nothing here
-- inverts one.
--
-- And the corpus cannot represent the event anyway. The capture records a row each time a value
-- CHANGES, iterating the periods each version contains, so a period the publisher drops emits
-- nothing at all and its absence is indistinguishable from it simply not being mentioned again.
--
-- So the claim is withdrawn rather than defended. Detecting a disappearance needs the capture to
-- record period sets per version, which it does not, and asserting the silence meanwhile is
-- exactly the shape of enforcement this portfolio keeps finding described in prose and running
-- nowhere.

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
