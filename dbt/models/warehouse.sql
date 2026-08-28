{{ config(materialized="table") }}

-- What the warehouse already holds: the latest value for each period as the publisher had it at
-- the cut-off. One row per (series, period), which is what a warehouse looks like to everybody
-- who reads it.
--
-- The as-of filter compares DATE PREFIXES rather than whole strings. A cut-off of "2023-06"
-- means the end of that month, and '2023-06-14' > '2023-06' lexically, so a plain comparison
-- would drop every release inside the cut-off month.

select series, period, value, released, version
from (
    select
        *,
        row_number() over (
            partition by series, period order by released desc, version desc
        ) as recency
    from {{ ref("observations") }}
    where substr(released, 1, length('{{ var("warehouse_as_at") }}')) <= '{{ var("warehouse_as_at") }}'
)
where recency = 1
