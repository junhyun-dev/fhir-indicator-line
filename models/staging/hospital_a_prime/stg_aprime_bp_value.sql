-- D1-D3 / ADR0006,0009,0013: original namespace/values; no KCD candidate fallback.
{{ config(materialized='table') }}
with raw as (
{% if env_var('A_PRIME_SOURCE_DIR', '') %}
select coalesce(cast("person_id" as varchar), '') as "person_id",
       coalesce(cast("observation_id" as varchar), '') as "observation_id",
       coalesce(cast("effective" as varchar), '') as "effective",
       coalesce(cast("status" as varchar), '') as "status",
       coalesce(cast("panel_code" as varchar), '') as "panel_code",
       coalesce(cast("panel_system" as varchar), '') as "panel_system",
       coalesce(cast("panel_codings" as varchar), '') as "panel_codings",
       coalesce(cast("bp_text" as varchar), '') as "bp_text",
       coalesce(cast("format_status" as varchar), '') as "format_status",
       coalesce(cast("systolic_code" as varchar), '') as "systolic_code",
       coalesce(cast("systolic_system" as varchar), '') as "systolic_system",
       coalesce(cast("systolic_original_value" as varchar), '') as "systolic_original_value",
       coalesce(cast("systolic_unit_code" as varchar), '') as "systolic_unit_code",
       coalesce(cast("systolic_unit_system" as varchar), '') as "systolic_unit_system",
       coalesce(cast("systolic_unit_display" as varchar), '') as "systolic_unit_display",
       coalesce(cast("diastolic_code" as varchar), '') as "diastolic_code",
       coalesce(cast("diastolic_system" as varchar), '') as "diastolic_system",
       coalesce(cast("diastolic_original_value" as varchar), '') as "diastolic_original_value",
       coalesce(cast("diastolic_unit_code" as varchar), '') as "diastolic_unit_code",
       coalesce(cast("diastolic_unit_system" as varchar), '') as "diastolic_unit_system",
       coalesce(cast("diastolic_unit_display" as varchar), '') as "diastolic_unit_display",
       coalesce(cast("derived_from" as varchar), '') as "derived_from"
from {{ source('a_prime', 'bp_details') }}
{% else %}
select cast('' as varchar) as "person_id",
       cast('' as varchar) as "observation_id",
       cast('' as varchar) as "effective",
       cast('' as varchar) as "status",
       cast('' as varchar) as "panel_code",
       cast('' as varchar) as "panel_system",
       cast('' as varchar) as "panel_codings",
       cast('' as varchar) as "bp_text",
       cast('' as varchar) as "format_status",
       cast('' as varchar) as "systolic_code",
       cast('' as varchar) as "systolic_system",
       cast('' as varchar) as "systolic_original_value",
       cast('' as varchar) as "systolic_unit_code",
       cast('' as varchar) as "systolic_unit_system",
       cast('' as varchar) as "systolic_unit_display",
       cast('' as varchar) as "diastolic_code",
       cast('' as varchar) as "diastolic_system",
       cast('' as varchar) as "diastolic_original_value",
       cast('' as varchar) as "diastolic_unit_code",
       cast('' as varchar) as "diastolic_unit_system",
       cast('' as varchar) as "diastolic_unit_display",
       cast('' as varchar) as "derived_from"
where false
{% endif %}
)
select raw.*, 'A_PRIME'::varchar as hospital,
       raw.observation_id || ':' || component.source_code as source_row_key,
       component.source_code, component.source_system, component.original_value,
       component.unit_code as unit_mapping_code, component.unit_system,
       component.unit_display, component.value_text as parsed_value_text,
       try_cast(nullif(component.value_text,'') as decimal(38,12)) as value,
       cast(nullif(substr(effective,1,10),'') as date) as bp_day, cast(nullif(substr(effective,1,10),'') as date) as record_day,
       case when component.source_system='http://loinc.org' and exists (
           select 1 from json_each(try_cast(raw.panel_codings as json)) coding
           where json_extract_string(coding.value,'$.code')='85354-9'
             and json_extract_string(coding.value,'$.system')='http://loinc.org')
           then 'hospital_a_prime_bp' else 'hospital_a_prime_bp_unmapped' end::varchar as source_vocabulary_id,
       case when component.unit_system='http://unitsofmeasure.org'
            then 'hospital_a_prime_unit' else 'hospital_a_prime_unit_unmapped' end::varchar as unit_vocabulary_id,
       component.unit_code as unit_source_value, component.value_text as value_source_value,
       true as is_omop_bp
from raw
cross join lateral (values
    (systolic_code,systolic_system,systolic_original_value,systolic_unit_code,systolic_unit_system,systolic_unit_display,split_part(bp_text,'/',1)),
    (diastolic_code,diastolic_system,diastolic_original_value,diastolic_unit_code,diastolic_unit_system,diastolic_unit_display,split_part(bp_text,'/',2))
) component(source_code,source_system,original_value,unit_code,unit_system,unit_display,value_text)
where component.source_code <> ''
