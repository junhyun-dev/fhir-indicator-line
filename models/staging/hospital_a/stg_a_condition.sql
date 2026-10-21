-- D1,D2 / decisions 0006,0009,0011: original diagnosis rows and written dates.
select distinct 'A'::varchar as hospital, r.id::varchar as source_row_key,
       regexp_extract(json_extract_string(r.payload_json, '$.subject.reference'), '[^:]+$', 0) as person_id,
       json_extract_string(coding.value, '$.code') as source_code,
       {{ fhir_day("json_extract_string(r.payload_json, '$.onsetDateTime')") }} as start_day,
       {{ fhir_day("json_extract_string(r.payload_json, '$.abatementDateTime')") }} as end_day,
       {{ fhir_day("coalesce(json_extract_string(r.payload_json, '$.recordedDate'), json_extract_string(r.payload_json, '$.onsetDateTime'))") }} as record_day,
       'hospital_a_dx'::varchar as source_vocabulary_id
from {{ source('fhir', 'latest_resources') }} r
cross join json_each(json_extract(r.payload_json, '$.code.coding')) coding
where r.resource_type = 'Condition'
