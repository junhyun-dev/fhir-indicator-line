-- D1-D3 / ADR0006,0009,0013: original namespace/values; no KCD candidate fallback.
{{ config(materialized='table') }}
with raw as (
{% if env_var('A_PRIME_SOURCE_DIR', '') %}
select coalesce(cast("person_id" as varchar), '') as "person_id",
       coalesce(cast("encounter_id" as varchar), '') as "encounter_id",
       coalesce(cast("class_code" as varchar), '') as "class_code",
       coalesce(cast("class_system" as varchar), '') as "class_system",
       coalesce(cast("start" as varchar), '') as "start",
       coalesce(cast("end" as varchar), '') as "end",
       coalesce(cast("recorded" as varchar), '') as "recorded",
       coalesce(cast("visit_kind" as varchar), '') as "visit_kind",
       coalesce(cast("derived_from" as varchar), '') as "derived_from"
from {{ source('a_prime', 'visits') }}
{% else %}
select cast('' as varchar) as "person_id",
       cast('' as varchar) as "encounter_id",
       cast('' as varchar) as "class_code",
       cast('' as varchar) as "class_system",
       cast('' as varchar) as "start",
       cast('' as varchar) as "end",
       cast('' as varchar) as "recorded",
       cast('' as varchar) as "visit_kind",
       cast('' as varchar) as "derived_from"
where false
{% endif %}
)
select raw.*, 'A_PRIME'::varchar as hospital,
       encounter_id::varchar as source_row_key, class_code as source_code,
       case when class_system='http://terminology.hl7.org/CodeSystem/v3-ActCode'
            then 'hospital_a_prime_visit' else 'hospital_a_prime_visit_unmapped' end::varchar as source_vocabulary_id,
       cast(nullif(substr("start",1,10),'') as date) as start_day, cast(nullif(substr("end",1,10),'') as date) as end_day,
       {{ fhir_day('recorded') }} as record_day
from raw
