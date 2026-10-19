-- D1,D2,D3 / t07,t09,t12,t14: preserve class and written period dates.
select id as encounter_id,
       regexp_extract(json_extract_string(payload_json, '$.subject.reference'), '[^:]+$', 0) as person_id,
       json_extract_string(payload_json, '$.class.code') as class_code,
       {{ fhir_day("json_extract_string(payload_json, '$.period.start')") }} as start_day,
       {{ fhir_day("json_extract_string(payload_json, '$.period.end')") }} as end_day,
       {{ fhir_day("json_extract_string(payload_json, '$.period.start')") }} as record_day
from {{ source('fhir', 'latest_resources') }}
where resource_type = 'Encounter'
