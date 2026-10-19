-- D1,D2,M2 / t10: union diagnoses, then map by hospital/code; system is descriptive.
with hospital_rows as (
    select hospital, condition_id, person_id, source_code, start_day, end_day, record_day
    from {{ ref('stg_a_condition') }}
    union all
    select hospital, condition_id, person_id, source_code, start_day, end_day, record_day
    from {{ ref('stg_b_condition') }}
)
select diagnosis.hospital, diagnosis.condition_id, diagnosis.person_id, diagnosis.source_code,
       mapping.concept, diagnosis.start_day, diagnosis.end_day, diagnosis.record_day
from hospital_rows diagnosis
join {{ ref('code_map') }} mapping
  on mapping.hospital = diagnosis.hospital and mapping.source_code = diagnosis.source_code
where mapping.concept = 'essential_hypertension'
