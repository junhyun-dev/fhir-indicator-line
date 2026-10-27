-- D1,D2,D5-D7 / ADR0001,0003,0010: maximum day + that exact row, not component-wise last values.
with daily_with_label as (
    select d.*, p.as_of_label from q1_reference d
    join periods p using (hospital, person_id, as_of)
), eligible as (
    select p.hospital, p.person_id, p.as_of_label, p.as_of
    from periods p
    where p.age_at_year_end between 18 and 85
      and exists (
          select 1 from condition_occurrence d join indicator_concepts s
            on s.concept_id = d.condition_concept_id and s.concept_set = 'essential_hypertension'
          where d.person_id = p.omop_person_id
            and d.condition_start_date <= p.hypertension_cutoff_day and d.condition_start_date <= p.as_of
            and (d.condition_end_date is null or d.condition_end_date >= p.measurement_start_day)
      )
      and exists (
          select 1 from visit_occurrence v join indicator_concepts s
            on s.concept_id = v.visit_concept_id and s.concept_set = 'outpatient_visit'
          where v.person_id = p.omop_person_id and v.visit_start_date between p.measurement_start_day and p.period_end_day
      )
), max_days as (
    select hospital, person_id, as_of, max(bp_date) as last_bp_date
    from daily_with_label group by hospital, person_id, as_of
), last_values as (
    select e.hospital, e.person_id, e.as_of_label, e.as_of, m.last_bp_date,
           d.systolic_min as systolic, d.diastolic_min as diastolic
    from eligible e left join max_days m using (hospital, person_id, as_of)
    left join daily_with_label d on d.hospital=e.hospital and d.person_id=e.person_id and d.as_of=e.as_of
      and d.bp_date=m.last_bp_date
)
select *, cast(last_bp_date is not null and systolic is not null and diastolic is not null
               and systolic < 140 and diastolic < 90 as integer) as controlled,
       case when last_bp_date is null then '혈압 없음'
            when systolic is null or diastolic is null then '마지막 날에 한쪽 값만'
            when systolic >= 140 then '수축기 140 이상'
            when diastolic >= 90 then '이완기 90 이상'
            else '조절됨' end as reason
from last_values
