-- D1,D3,D4,M2 / t05,t07,t08,t14,t15: one hospital/label/person/day with usable values.
select periods.hospital, periods.as_of_label, periods.person_id, bp.bp_day as bp_date,
       min(case when bp.concept = 'systolic' then bp.value end) as systolic_min,
       min(case when bp.concept = 'diastolic' then bp.value end) as diastolic_min
from {{ ref('bp_value') }} bp
join {{ ref('person_period') }} periods
  on periods.hospital = bp.hospital and periods.person_id = bp.person_id
where bp.bp_day between periods.measurement_start_day and periods.period_end_day
  and (bp.record_day is null or bp.record_day <= periods.as_of)
  and bp.value is not null
  and not exists (
      select 1
      from {{ ref('visit') }} visits
      where visits.hospital = periods.hospital and visits.person_id = periods.person_id
        and visits.visit_type = 'inpatient_or_ed'
        and (visits.record_day is null or visits.record_day <= periods.as_of)
        and bp.bp_day between visits.start_day and coalesce(visits.end_day, visits.start_day)
  )
group by periods.hospital, periods.as_of_label, periods.person_id, bp.bp_day
