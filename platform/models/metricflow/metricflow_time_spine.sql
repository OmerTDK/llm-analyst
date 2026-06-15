{{ config(materialized='table') }}

-- End date is a dbt variable (metricflow_time_spine_end) so callers with a
-- later data horizon can extend the spine without touching this file. The
-- default (2035-01-01) is far enough beyond the current 24-cohort synthetic
-- book that `make generate` with any plausible --cohort-count and --start-month
-- will never produce dates outside the spine. A hard-coded 2026-01-01 would
-- silently drop metric_time rows for synthetic books with later start dates.
with days as (
    {{ dbt.date_spine(
        'day',
        "make_date(2018, 1, 1)",
        "make_date(" ~ var('metricflow_time_spine_end', '2035, 1, 1') ~ ")"
    ) }}
)

select cast(date_day as date) as date_day
from days
