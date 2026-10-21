-- D1,D3,D4 / decisions 0004,0006,0008,0010: valid daily component minima from OMOP.
select periods.hospital, periods.as_of_label, periods.person_id, bp.measurement_date as bp_date,
       min(case when meaning.concept_set = 'systolic' then cast(bp.value_as_number as double) end) as systolic_min,
       min(case when meaning.concept_set = 'diastolic' then cast(bp.value_as_number as double) end) as diastolic_min
from {{ ref('measurement') }} bp
join {{ ref('indicator_concepts') }} meaning
  on meaning.concept_id = bp.measurement_concept_id
 and meaning.concept_set in ('systolic', 'diastolic')
join {{ ref('int_person_period') }} periods on periods.omop_person_id = bp.person_id
where bp.measurement_date between periods.measurement_start_day and periods.period_end_day
  and bp.value_as_number is not null
  and exists (
      select 1 from {{ ref('indicator_concepts') }} unit
      where unit.concept_set = 'bp_unit' and unit.concept_id = bp.unit_concept_id
  )
  and not exists (
      select 1
      from {{ ref('visit_occurrence') }} visits
      join {{ ref('indicator_concepts') }} excluded
        on excluded.concept_id = visits.visit_concept_id and excluded.concept_set = 'inpatient_or_ed_visit'
      where visits.person_id = periods.omop_person_id
        and bp.measurement_date between visits.visit_start_date and visits.visit_end_date
  )
group by periods.hospital, periods.as_of_label, periods.person_id, bp.measurement_date
