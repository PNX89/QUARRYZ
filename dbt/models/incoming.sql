{{ config(materialized="table") }}

-- The load arriving: the same shape, as the publisher had it at the later cut-off.

select series, period, value, released, version
from (
    select
        *,
        row_number() over (
            partition by series, period order by released desc, version desc
        ) as recency
    from {{ ref("observations") }}
    where substr(released, 1, length('{{ var("incoming_as_at") }}')) <= '{{ var("incoming_as_at") }}'
)
where recency = 1
