-- D1-D3 / ADR0006,0009,0013: original namespace/values; no KCD candidate fallback.
{{ config(materialized='table') }}
with raw as (
{% if env_var('A_PRIME_SOURCE_DIR', '') %}
select coalesce(cast("person_id" as varchar), '') as "person_id",
       coalesce(cast("birth_date" as varchar), '') as "birth_date",
       coalesce(cast("gender" as varchar), '') as "gender",
       coalesce(cast("deceased_datetime" as varchar), '') as "deceased_datetime",
       coalesce(cast("deceased_boolean" as varchar), '') as "deceased_boolean",
       coalesce(cast("measurement_year" as varchar), '') as "measurement_year",
       coalesce(cast("derived_from" as varchar), '') as "derived_from"
from {{ source('a_prime', 'persons') }}
{% else %}
select cast('' as varchar) as "person_id",
       cast('' as varchar) as "birth_date",
       cast('' as varchar) as "gender",
       cast('' as varchar) as "deceased_datetime",
       cast('' as varchar) as "deceased_boolean",
       cast('' as varchar) as "measurement_year",
       cast('' as varchar) as "derived_from"
where false
{% endif %}
)
select raw.* exclude(measurement_year), try_cast(measurement_year as integer) as measurement_year, 'A_PRIME'::varchar as hospital,
       try_cast(substr(birth_date,1,4) as integer) as year_of_birth,
       nullif(gender,'') as gender_source_value,
       'hospital_a_prime_gender'::varchar as gender_vocabulary_id
from raw
