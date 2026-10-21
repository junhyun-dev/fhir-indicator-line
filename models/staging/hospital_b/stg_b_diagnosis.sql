-- D1,D2 / decisions 0006,0009,0011: each original versioned diagnosis, before mapping.
{{ config(materialized='table') }}
select 'B'::varchar as hospital, diagnosis.subject_id as person_id,
       diagnosis.subject_id || ':' || diagnosis.hadm_id || ':' || diagnosis.seq_num
         || ':' || diagnosis.icd_version || ':' || diagnosis.icd_code as source_row_key,
       diagnosis.icd_code as source_code,
       'hospital_b_icd' || diagnosis.icd_version as source_vocabulary_id,
       {{ fhir_day('admission.admittime') }} as start_day,
       null::date as end_day,
       {{ fhir_day('admission.admittime') }} as record_day
from {{ source('mimic', 'diagnoses_icd') }} diagnosis
left join {{ source('mimic', 'admissions') }} admission
  on admission.subject_id = diagnosis.subject_id and admission.hadm_id = diagnosis.hadm_id
