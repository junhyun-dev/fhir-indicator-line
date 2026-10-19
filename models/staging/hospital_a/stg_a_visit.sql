-- D1,D2,D3,M2 / t07,t09,t12,t14: only A's adapter interprets Encounter.class.
select 'A'::varchar as hospital, id as visit_id,
       regexp_extract(json_extract_string(payload_json, '$.subject.reference'), '[^:]+$', 0) as person_id,
       case when json_extract_string(payload_json, '$.class.code') = 'AMB' then 'outpatient'
            when json_extract_string(payload_json, '$.class.code') in ('IMP', 'EMER') then 'inpatient_or_ed'
            else 'other' end as visit_type,
       {{ fhir_day("json_extract_string(payload_json, '$.period.start')") }} as start_day,
       {{ fhir_day("json_extract_string(payload_json, '$.period.end')") }} as end_day,
       {{ fhir_day("json_extract_string(payload_json, '$.period.start')") }} as record_day
from {{ source('fhir', 'latest_resources') }}
where resource_type = 'Encounter'
