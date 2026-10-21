-- D1,D2 / decisions 0002,0005,0010: one person's original facts; no indicator calendar.
select 'A'::varchar as hospital, id::varchar as person_id,
       year({{ fhir_day("json_extract_string(payload_json, '$.birthDate')") }})::integer as year_of_birth,
       nullif(json_extract_string(payload_json, '$.gender'), '') as gender_source_value,
       2025::integer as measurement_year,
       'hospital_a_gender'::varchar as gender_vocabulary_id
from {{ source('fhir', 'latest_resources') }}
where resource_type = 'Patient'
