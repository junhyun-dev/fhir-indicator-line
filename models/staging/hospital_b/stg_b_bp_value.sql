-- D1,D3 / decisions 0006,0008,0009,0011: split BP values without losing original text.
{{ config(materialized='table') }}
with omr_bp as (
    select subject_id as person_id,
           'omr_bp:' || subject_id || ':' || chartdate || ':' || seq_num as observation_id,
           {{ fhir_day('chartdate') }} as bp_day, result_value,
           subject_id || ':' || chartdate || ':' || seq_num as original_key
    from {{ source('mimic', 'omr') }}
    where result_name = 'Blood Pressure'
), omr_values as (
    select observation_id, person_id, 'omr_systolic'::varchar as source_code,
           try_cast(split_part(result_value, '/', 1) as double) as value, bp_day, result_value, original_key
    from omr_bp
    union all
    select observation_id, person_id, 'omr_diastolic'::varchar as source_code,
           try_cast(split_part(result_value, '/', 2) as double) as value, bp_day, result_value, original_key
    from omr_bp
)
select 'B'::varchar as hospital, observation_id, person_id, source_code,
       value, ''::varchar as source_unit, bp_day, bp_day as record_day,
       'hospital_b_omr'::varchar as source_vocabulary_id,
       'hospital_b_omr_unit'::varchar as unit_vocabulary_id,
       'OMR_BP_NO_UNIT'::varchar as unit_mapping_code,
       null::varchar as unit_source_value, result_value::varchar as value_source_value,
       original_key || ':' || source_code as source_row_key, true as is_omop_bp
from omr_values
union all
select 'B'::varchar as hospital,
       'icu:' || subject_id || ':' || hadm_id || ':' || stay_id || ':' || itemid || ':'
         || charttime || ':' || storetime as observation_id,
       subject_id as person_id, itemid as source_code,
       try_cast(valuenum as double) as value, valueuom as source_unit,
       {{ fhir_day('charttime') }} as bp_day, {{ fhir_day('charttime') }} as record_day,
       'hospital_b_icu'::varchar as source_vocabulary_id,
       'hospital_b_icu_unit'::varchar as unit_vocabulary_id,
       nullif(valueuom, '') as unit_mapping_code,
       nullif(valueuom, '') as unit_source_value, chart.value::varchar as value_source_value,
       'icu:' || subject_id || ':' || hadm_id || ':' || stay_id || ':' || itemid || ':'
         || charttime || ':' || storetime || ':' || itemid as source_row_key, true as is_omop_bp
from {{ source('mimic', 'chartevents') }} chart
where itemid in ('220179', '220180')
