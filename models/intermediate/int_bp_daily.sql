-- D1,D3,D4 / t05,t07,t08,t14,t15: one as_of/person/day with at least one usable value.
select dates.as_of, bp.person_id, bp.bp_day as bp_date,
       min(case when bp.component_type = 'systolic' then bp.value end) as systolic_min,
       min(case when bp.component_type = 'diastolic' then bp.value end) as diastolic_min
from {{ ref('stg_bp_component') }} bp
cross join {{ ref('stg_as_of_dates') }} dates
where bp.bp_day between dates.measurement_start_day and dates.period_end_day
  and (bp.record_day is null or bp.record_day <= dates.as_of)
  and bp.unit_code = 'mm[Hg]'
  and bp.value is not null
  and not exists (
      select 1
      from {{ ref('stg_encounter') }} encounter
      where encounter.person_id = bp.person_id
        and encounter.class_code in ('IMP', 'EMER')
        and (encounter.record_day is null or encounter.record_day <= dates.as_of)
        and bp.bp_day between encounter.start_day and coalesce(encounter.end_day, encounter.start_day)
  )
group by dates.as_of, bp.person_id, bp.bp_day
