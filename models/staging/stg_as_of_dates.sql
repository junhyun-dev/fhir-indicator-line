-- D1 / t06,t12,t14: measurement calendar and cutoff dates enter through L3.
with dates as (
    select cast(as_of as date) as as_of,
           date '2025-01-01' as measurement_start_day,
           date '2025-12-31' as measurement_end_day
    from {{ ref('as_of_dates') }}
)
select as_of, measurement_start_day, measurement_end_day,
       least(measurement_end_day, as_of) as period_end_day
from dates
