-- D1,D3,D4 / ADR0004,0008,0010: exclude a set of days, reduce components before period expansion.
with usable as (
    select bp.person_id, bp.measurement_date, meaning.concept_set, bp.value_as_number
    from measurement bp
    join indicator_concepts meaning on meaning.concept_id = bp.measurement_concept_id
     and meaning.concept_set in ('systolic', 'diastolic')
    where bp.value_as_number is not null
      and exists (select 1 from indicator_concepts u where u.concept_set = 'bp_unit' and u.concept_id = bp.unit_concept_id)
), excluded_days as (
    select distinct u.person_id, u.measurement_date
    from usable u join visit_occurrence v on v.person_id = u.person_id
      and u.measurement_date between v.visit_start_date and v.visit_end_date
    join indicator_concepts x on x.concept_set = 'inpatient_or_ed_visit' and x.concept_id = v.visit_concept_id
), components as (
    select u.person_id, u.measurement_date, u.concept_set, min(u.value_as_number) as value
    from usable u left join excluded_days e using (person_id, measurement_date)
    where e.person_id is null
    group by u.person_id, u.measurement_date, u.concept_set
), daily as (
    select person_id, measurement_date as bp_date,
           max(case when concept_set = 'systolic' then value end)::double as systolic_min,
           max(case when concept_set = 'diastolic' then value end)::double as diastolic_min
    from components group by person_id, measurement_date
)
select p.hospital, p.person_id, p.as_of, d.bp_date, d.systolic_min, d.diastolic_min
from daily d join periods p on p.omop_person_id = d.person_id
 and d.bp_date between p.measurement_start_day and p.period_end_day
