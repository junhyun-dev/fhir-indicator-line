-- D1,D2,D5,D6,D7 / t01-t15: eligibility and person classification live here; no D7 exclusions.
with eligible as (
    select patient.person_id, dates.as_of
    from {{ ref('stg_patient') }} patient
    cross join {{ ref('stg_as_of_dates') }} dates
    where year(dates.measurement_end_day) - year(patient.birth_date) between 18 and 85
      and exists (
          select 1
          from {{ ref('stg_condition') }} diagnosis
          where diagnosis.person_id = patient.person_id
            and (diagnosis.record_day is null or diagnosis.record_day <= dates.as_of)
            and diagnosis.onset_day <= make_date(year(dates.measurement_end_day), 6, 30)
            and (diagnosis.abatement_day is null or diagnosis.abatement_day >= dates.measurement_start_day)
      )
      and exists (
          select 1
          from {{ ref('stg_encounter') }} encounter
          where encounter.person_id = patient.person_id
            and encounter.class_code = 'AMB'
            and (encounter.record_day is null or encounter.record_day <= dates.as_of)
            and encounter.start_day between dates.measurement_start_day and dates.period_end_day
      )
), ranked_days as (
    select as_of, person_id, bp_date, systolic_min, diastolic_min,
           row_number() over (partition by as_of, person_id order by bp_date desc) as day_rank
    from {{ ref('int_bp_daily') }}
), last_values as (
    select eligible.person_id, eligible.as_of, daily.bp_date as last_bp_date,
           daily.systolic_min as systolic, daily.diastolic_min as diastolic
    from eligible
    left join ranked_days daily
      on daily.person_id = eligible.person_id and daily.as_of = eligible.as_of and daily.day_rank = 1
), classified as (
    select *,
           case when last_bp_date is null then '혈압 없음'
                when systolic is null or diastolic is null then '마지막 날에 한쪽 값만'
                when systolic >= 140 then '수축기 140 이상'
                when diastolic >= 90 then '이완기 90 이상'
                else '조절됨' end as reason
    from last_values
)
select person_id, as_of, last_bp_date, systolic, diastolic,
       cast(reason = '조절됨' as integer) as controlled, reason
from classified
