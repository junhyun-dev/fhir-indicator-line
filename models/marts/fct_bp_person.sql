-- D1,D2,D5,D6,D7,M2 / t01-t15: eligibility stays here, using only common meanings.
with eligible as (
    select periods.hospital, periods.as_of_label, periods.person_id, periods.as_of
    from {{ ref('person_period') }} periods
    where periods.age_at_year_end between 18 and 85
      and exists (
          select 1
          from {{ ref('condition') }} diagnosis
          where diagnosis.hospital = periods.hospital and diagnosis.person_id = periods.person_id
            and diagnosis.concept = 'essential_hypertension'
            and (diagnosis.record_day is null or diagnosis.record_day <= periods.as_of)
            and diagnosis.start_day <= periods.hypertension_cutoff_day
            and (diagnosis.end_day is null or diagnosis.end_day >= periods.measurement_start_day)
      )
      and exists (
          select 1
          from {{ ref('visit') }} visits
          where visits.hospital = periods.hospital and visits.person_id = periods.person_id
            and visits.visit_type = 'outpatient'
            and (visits.record_day is null or visits.record_day <= periods.as_of)
            and visits.start_day between periods.measurement_start_day and periods.period_end_day
      )
), ranked_days as (
    select hospital, as_of_label, person_id, bp_date, systolic_min, diastolic_min,
           row_number() over (partition by hospital, as_of_label, person_id order by bp_date desc) as day_rank
    from {{ ref('int_bp_daily') }}
), last_values as (
    select eligible.hospital, eligible.as_of_label, eligible.person_id, eligible.as_of, daily.bp_date as last_bp_date,
           daily.systolic_min as systolic, daily.diastolic_min as diastolic
    from eligible
    left join ranked_days daily
      on daily.hospital = eligible.hospital and daily.as_of_label = eligible.as_of_label
     and daily.person_id = eligible.person_id and daily.day_rank = 1
), classified as (
    select *,
           case when last_bp_date is null then '혈압 없음'
                when systolic is null or diastolic is null then '마지막 날에 한쪽 값만'
                when systolic >= 140 then '수축기 140 이상'
                when diastolic >= 90 then '이완기 90 이상'
                else '조절됨' end as reason
    from last_values
)
select hospital, as_of_label, person_id, as_of, last_bp_date, systolic, diastolic,
       cast(reason = '조절됨' as integer) as controlled, reason
from classified
