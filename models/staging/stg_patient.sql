-- D1,D2 / t11,t14: one patient; eligibility remains in L5.
select id as person_id,
       {{ fhir_day("json_extract_string(payload_json, '$.birthDate')") }} as birth_date
from {{ source('fhir', 'latest_resources') }}
where resource_type = 'Patient'
