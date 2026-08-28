-- THE BUILD FAILS HERE. A singular dbt test fails when its query returns rows, so this is the
-- line that turns a publisher rewriting history into a red build rather than a quiet update to
-- last quarter's research.
--
-- The message a reader gets is the model's own `why` column, which names the release and the
-- count, because "test failed" without the release is a test somebody disables.

select series, revised_at, periods, periods_expected, why
from {{ ref("undeclared_revisions") }}
