-- D1,D3/M2B: split exact OMR BP rows; ICU values keep their itemid and original unit.
{{ config(materialized='table') }}
with omr_bp as (
    select subject_id as person_id,
           'omr_bp:' || subject_id || ':' || chartdate || ':' || seq_num as observation_id,
           {{ fhir_day('chartdate') }} as bp_day, result_value
    from {{ source('mimic', 'omr') }}
    where result_name = 'Blood Pressure'
), omr_values as (
    select observation_id, person_id, 'omr_systolic'::varchar as source_code,
           try_cast(split_part(result_value, '/', 1) as double) as value, bp_day
    from omr_bp
    union all
    select observation_id, person_id, 'omr_diastolic'::varchar as source_code,
           try_cast(split_part(result_value, '/', 2) as double) as value, bp_day
    from omr_bp
)
select 'B'::varchar as hospital, observation_id, person_id, source_code,
       value, ''::varchar as source_unit, bp_day, bp_day as record_day
from omr_values
union all
select 'B'::varchar as hospital,
       'icu:' || subject_id || ':' || hadm_id || ':' || stay_id || ':' || itemid || ':'
         || charttime || ':' || storetime as observation_id,
       subject_id as person_id, itemid as source_code,
       try_cast(valuenum as double) as value, valueuom as source_unit,
       {{ fhir_day('charttime') }} as bp_day, {{ fhir_day('charttime') }} as record_day
from {{ source('mimic', 'chartevents') }}
where itemid in ('220179', '220180')
