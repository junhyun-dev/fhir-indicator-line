-- D1,D2,D3/M2B: OMR days are outpatient only outside all admission/ED day intervals.
{{ config(materialized='table') }}
with admissions as (
    select subject_id as person_id, hadm_id,
           {{ fhir_day("coalesce(nullif(edregtime, ''), admittime)") }} as start_day,
           {{ fhir_day('dischtime') }} as end_day
    from {{ source('mimic', 'admissions') }}
), omr_days as (
    select distinct subject_id as person_id, {{ fhir_day('chartdate') }} as visit_day
    from {{ source('mimic', 'omr') }}
)
select 'B'::varchar as hospital, 'admission:' || hadm_id as visit_id,
       person_id, 'inpatient_or_ed'::varchar as visit_type, start_day, end_day, start_day as record_day
from admissions
union all
select 'B'::varchar as hospital,
       'omr:' || omr.person_id || ':' || cast(omr.visit_day as varchar) as visit_id,
       omr.person_id, 'outpatient'::varchar as visit_type,
       omr.visit_day as start_day, omr.visit_day as end_day, omr.visit_day as record_day
from omr_days omr
where not exists (
    select 1 from admissions admission
    where admission.person_id = omr.person_id
      and omr.visit_day between admission.start_day and coalesce(admission.end_day, admission.start_day)
)
