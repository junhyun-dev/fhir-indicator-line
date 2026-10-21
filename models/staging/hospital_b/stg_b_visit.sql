-- D1,D2,D3 / decisions 0006,0009,0011: preserve B visit origins and existing intervals.
{{ config(materialized='table') }}
with admissions as (
    select subject_id as person_id, hadm_id,
           case when nullif(edregtime, '') is not null then 'ed_admission' else 'admission' end as source_code,
           {{ fhir_day("coalesce(nullif(edregtime, ''), admittime)") }} as start_day,
           {{ fhir_day('dischtime') }} as end_day
    from {{ source('mimic', 'admissions') }}
), omr_days as (
    select distinct subject_id as person_id, {{ fhir_day('chartdate') }} as visit_day
    from {{ source('mimic', 'omr') }}
)
select 'B'::varchar as hospital, person_id, start_day, end_day, start_day as record_day,
       source_code, 'hospital_b_visit'::varchar as source_vocabulary_id,
       hadm_id::varchar as source_row_key
from admissions
union all
select 'B'::varchar as hospital, omr.person_id,
       omr.visit_day as start_day, omr.visit_day as end_day, omr.visit_day as record_day,
       'omr_day'::varchar as source_code, 'hospital_b_visit'::varchar as source_vocabulary_id,
       omr.person_id || ':' || cast(omr.visit_day as varchar) as source_row_key
from omr_days omr
where not exists (
    select 1 from admissions admission
    where admission.person_id = omr.person_id
      and omr.visit_day between admission.start_day and coalesce(admission.end_day, admission.start_day)
)
