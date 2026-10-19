-- D1,D2 / t01,t10,t14: flatten codes and match the seed by code only.
select distinct r.id as condition_id,
       json_extract_string(coding.value, '$.code') as code,
       regexp_extract(json_extract_string(r.payload_json, '$.subject.reference'), '[^:]+$', 0) as person_id,
       {{ fhir_day("json_extract_string(r.payload_json, '$.onsetDateTime')") }} as onset_day,
       {{ fhir_day("json_extract_string(r.payload_json, '$.abatementDateTime')") }} as abatement_day,
       {{ fhir_day("coalesce(json_extract_string(r.payload_json, '$.recordedDate'), json_extract_string(r.payload_json, '$.onsetDateTime'))") }} as record_day
from {{ source('fhir', 'latest_resources') }} r
cross join json_each(json_extract(r.payload_json, '$.code.coding')) coding
join {{ ref('hypertension_codes') }} codes
  on json_extract_string(coding.value, '$.code') = codes.code
where r.resource_type = 'Condition'
