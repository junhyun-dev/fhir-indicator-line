-- D1,D2,M2 / t10,t14: A's diagnosis codes and written dates, before semantic mapping.
select distinct 'A'::varchar as hospital, r.id as condition_id,
       regexp_extract(json_extract_string(r.payload_json, '$.subject.reference'), '[^:]+$', 0) as person_id,
       json_extract_string(coding.value, '$.code') as source_code,
       {{ fhir_day("json_extract_string(r.payload_json, '$.onsetDateTime')") }} as start_day,
       {{ fhir_day("json_extract_string(r.payload_json, '$.abatementDateTime')") }} as end_day,
       {{ fhir_day("coalesce(json_extract_string(r.payload_json, '$.recordedDate'), json_extract_string(r.payload_json, '$.onsetDateTime'))") }} as record_day
from {{ source('fhir', 'latest_resources') }} r
cross join json_each(json_extract(r.payload_json, '$.code.coding')) coding
where r.resource_type = 'Condition'
