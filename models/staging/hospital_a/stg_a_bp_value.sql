-- D1,D3 / decisions 0006,0008,0009,0011: retain panel components and original units.
select distinct 'A'::varchar as hospital, r.id as observation_id,
       regexp_extract(json_extract_string(r.payload_json, '$.subject.reference'), '[^:]+$', 0) as person_id,
       json_extract_string(coding.value, '$.code') as source_code,
       try_cast(json_extract_string(component.value, '$.valueQuantity.value') as double) as value,
       json_extract_string(component.value, '$.valueQuantity.code') as source_unit,
       {{ fhir_day("json_extract_string(r.payload_json, '$.effectiveDateTime')") }} as bp_day,
       {{ fhir_day("json_extract_string(r.payload_json, '$.effectiveDateTime')") }} as record_day,
       'hospital_a_bp'::varchar as source_vocabulary_id,
       'hospital_a_unit'::varchar as unit_vocabulary_id,
       json_extract_string(component.value, '$.valueQuantity.code') as unit_mapping_code,
       json_extract_string(component.value, '$.valueQuantity.code') as unit_source_value,
       null::varchar as value_source_value,
       r.id || ':' || json_extract_string(coding.value, '$.code') as source_row_key,
       json_extract_string(coding.value, '$.code') in ('8480-6', '8462-4') as is_omop_bp
from {{ source('fhir', 'latest_resources') }} r
cross join json_each(json_extract(r.payload_json, '$.component')) component
cross join json_each(json_extract(component.value, '$.code.coding')) coding
where r.resource_type = 'Observation'
  and exists (
      select 1
      from json_each(json_extract(r.payload_json, '$.code.coding')) panel_code
      where json_extract_string(panel_code.value, '$.code') = '85354-9'
  )
