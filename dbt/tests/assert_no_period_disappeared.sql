-- A period vanishing from a load is a THIRD event, neither a new period nor a revision, and
-- nothing else in this project would notice it.
--
-- It has never happened in this corpus, which is exactly why it is asserted: an untested case
-- that has not occurred yet reads as coverage until the day it does.

select warehouse.series, warehouse.period
from {{ ref("warehouse") }} as warehouse
left join {{ ref("incoming") }} as incoming
    on warehouse.series = incoming.series
    and warehouse.period = incoming.period
where incoming.period is null
