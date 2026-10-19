-- D1,D2/M2B: retain the first admission for each person's versioned diagnosis code.
{{ config(materialized='table') }}
with diagnoses as (
    select diagnosis.subject_id as person_id, diagnosis.icd_version,
           diagnosis.icd_code as source_code,
           min({{ fhir_day('admission.admittime') }}) as start_day
    from {{ source('mimic', 'diagnoses_icd') }} diagnosis
    join {{ source('mimic', 'admissions') }} admission
      on admission.subject_id = diagnosis.subject_id and admission.hadm_id = diagnosis.hadm_id
    where (diagnosis.icd_version = '10' and diagnosis.icd_code = 'I10')
       or (diagnosis.icd_version = '9' and diagnosis.icd_code in ('4010', '4011', '4019'))
    group by diagnosis.subject_id, diagnosis.icd_version, diagnosis.icd_code
)
select 'B'::varchar as hospital,
       'icd:' || person_id || ':' || icd_version || ':' || source_code as condition_id,
       person_id, source_code, start_day, null::date as end_day, start_day as record_day
from diagnoses
