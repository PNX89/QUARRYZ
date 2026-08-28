{{ config(materialized="table") }}

-- Every recorded state of every observation, read straight from the committed corpus.
--
-- The four CSVs are the bitemporal table: one row each time a period's value changed, carrying
-- the version that changed it. Reading them with read_csv rather than seeding them keeps one
-- copy of the data in the repository instead of two.
--
-- `value` STAYS A STRING HERE. It carries WITHDRAWN for a value the publisher emptied, and
-- casting at this layer would turn that into a null and lose the distinction between "withdrawn
-- after publication" and "never published", which is the thing this warehouse exists to keep.

{% set series = ["IKBJ", "DZLS", "KAC3", "MGRZ"] %}

{% for cdid in series %}
select
    '{{ cdid }}' as series,
    period,
    value,
    released,
    version
from read_csv('{{ var("vintages") }}/{{ cdid }}.csv', header = true, columns = {
    'period': 'VARCHAR', 'value': 'VARCHAR', 'released': 'VARCHAR', 'version': 'VARCHAR'
})
{% if not loop.last %}union all{% endif %}
{% endfor %}
