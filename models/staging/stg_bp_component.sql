-- D1,D3 / t08,t13,t14: pair each value with its own component code, never its position.
select distinct r.id as observation_id,
       json_extract_string(coding.value, '$.code') as loinc_code,
       case when json_extract_string(coding.value, '$.code') = '8480-6'
            then 'systolic' else 'diastolic' end as component_type,
       regexp_extract(json_extract_string(r.payload_json, '$.subject.reference'), '[^:]+$', 0) as person_id,
       {{ fhir_day("json_extract_string(r.payload_json, '$.effectiveDateTime')") }} as bp_day,
       try_cast(json_extract_string(component.value, '$.valueQuantity.value') as double) as value,
       json_extract_string(component.value, '$.valueQuantity.code') as unit_code,
       {{ fhir_day("json_extract_string(r.payload_json, '$.effectiveDateTime')") }} as record_day
from {{ source('fhir', 'latest_resources') }} r
cross join json_each(json_extract(r.payload_json, '$.component')) component
cross join json_each(json_extract(component.value, '$.code.coding')) coding
where r.resource_type = 'Observation'
  and json_extract_string(coding.value, '$.code') in ('8480-6', '8462-4')
  and exists (
      select 1
      from json_each(json_extract(r.payload_json, '$.code.coding')) panel_code
      where json_extract_string(panel_code.value, '$.code') = '85354-9'
  )
