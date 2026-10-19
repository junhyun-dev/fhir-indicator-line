-- D1,D3,M2 / t08,t13,t14: retain the BP panel and each component's own code/value.
select distinct 'A'::varchar as hospital, r.id as observation_id,
       regexp_extract(json_extract_string(r.payload_json, '$.subject.reference'), '[^:]+$', 0) as person_id,
       json_extract_string(coding.value, '$.code') as source_code,
       try_cast(json_extract_string(component.value, '$.valueQuantity.value') as double) as value,
       json_extract_string(component.value, '$.valueQuantity.code') as source_unit,
       {{ fhir_day("json_extract_string(r.payload_json, '$.effectiveDateTime')") }} as bp_day,
       {{ fhir_day("json_extract_string(r.payload_json, '$.effectiveDateTime')") }} as record_day
from {{ source('fhir', 'latest_resources') }} r
cross join json_each(json_extract(r.payload_json, '$.component')) component
cross join json_each(json_extract(component.value, '$.code.coding')) coding
where r.resource_type = 'Observation'
  and exists (
      select 1
      from json_each(json_extract(r.payload_json, '$.code.coding')) panel_code
      where json_extract_string(panel_code.value, '$.code') = '85354-9'
  )
