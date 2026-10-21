-- D1-D3 / ADR0006,0009,0013: original namespace/values; no KCD candidate fallback.
{{ config(materialized='table') }}
with raw as (
{% if env_var('A_PRIME_SOURCE_DIR', '') %}
select coalesce(cast("person_id" as varchar), '') as "person_id",
       coalesce(cast("condition_id" as varchar), '') as "condition_id",
       coalesce(cast("coding_index" as varchar), '') as "coding_index",
       coalesce(cast("original_code" as varchar), '') as "original_code",
       coalesce(cast("original_system" as varchar), '') as "original_system",
       coalesce(cast("start" as varchar), '') as "start",
       coalesce(cast("end" as varchar), '') as "end",
       coalesce(cast("recorded" as varchar), '') as "recorded",
       coalesce(cast("clinical_status" as varchar), '') as "clinical_status",
       coalesce(cast("kcd_candidate_code" as varchar), '') as "kcd_candidate_code",
       coalesce(cast("kcd_candidate_edition_context" as varchar), '') as "kcd_candidate_edition_context",
       coalesce(cast("kcd_candidate_status" as varchar), '') as "kcd_candidate_status",
       coalesce(cast("kcd_candidate_usage" as varchar), '') as "kcd_candidate_usage",
       coalesce(cast("derived_from" as varchar), '') as "derived_from"
from {{ source('a_prime', 'diagnoses') }}
{% else %}
select cast('' as varchar) as "person_id",
       cast('' as varchar) as "condition_id",
       cast('' as varchar) as "coding_index",
       cast('' as varchar) as "original_code",
       cast('' as varchar) as "original_system",
       cast('' as varchar) as "start",
       cast('' as varchar) as "end",
       cast('' as varchar) as "recorded",
       cast('' as varchar) as "clinical_status",
       cast('' as varchar) as "kcd_candidate_code",
       cast('' as varchar) as "kcd_candidate_edition_context",
       cast('' as varchar) as "kcd_candidate_status",
       cast('' as varchar) as "kcd_candidate_usage",
       cast('' as varchar) as "derived_from"
where false
{% endif %}
)
select raw.*, 'A_PRIME'::varchar as hospital,
       condition_id::varchar as source_row_key, original_code as source_code,
       case when original_system='http://snomed.info/sct' then 'hospital_a_prime_dx_snomed'
            else 'hospital_a_prime_dx_unmapped' end::varchar as source_vocabulary_id,
       cast(nullif(substr("start",1,10),'') as date) as start_day, cast(nullif(substr("end",1,10),'') as date) as end_day,
       {{ fhir_day('recorded') }} as record_day
from raw
