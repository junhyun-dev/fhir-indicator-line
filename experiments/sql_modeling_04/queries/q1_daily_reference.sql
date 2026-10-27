-- D1,D3,D4 / ADR0004,0008,0010. Reference: frozen int_bp_daily semantics.
-- Input relation aliases and the final label->date projection are the only adapters.
with daily_by_label as (
    select periods.hospital, periods.as_of_label, periods.person_id, bp.measurement_date as bp_date,
           min(case when meaning.concept_set = 'systolic' then cast(bp.value_as_number as double) end) as systolic_min,
           min(case when meaning.concept_set = 'diastolic' then cast(bp.value_as_number as double) end) as diastolic_min
    from measurement bp
    join indicator_concepts meaning on meaning.concept_id = bp.measurement_concept_id
     and meaning.concept_set in ('systolic', 'diastolic')
    join periods on periods.omop_person_id = bp.person_id
    where bp.measurement_date between periods.measurement_start_day and periods.period_end_day
      and bp.value_as_number is not null
      and exists (select 1 from indicator_concepts unit where unit.concept_set = 'bp_unit' and unit.concept_id = bp.unit_concept_id)
      and not exists (
          select 1 from visit_occurrence visits
          join indicator_concepts excluded on excluded.concept_id = visits.visit_concept_id and excluded.concept_set = 'inpatient_or_ed_visit'
          where visits.person_id = periods.omop_person_id
            and bp.measurement_date between visits.visit_start_date and visits.visit_end_date
      )
    group by periods.hospital, periods.as_of_label, periods.person_id, bp.measurement_date
)
select d.hospital, d.person_id, p.as_of, d.bp_date, d.systolic_min, d.diastolic_min
from daily_by_label d join periods p using (hospital, person_id, as_of_label)
