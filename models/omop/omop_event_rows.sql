-- D1,D2,D3 / decisions 0007-0009,0011: number each carried event once, retain source keys.
{{ config(materialized='table') }}
with visits as (
    select hospital, person_id as source_person_id, source_row_key, source_code,
           source_vocabulary_id, start_day, end_day
    from {{ ref('stg_a_visit') }}
    union all
    select hospital, person_id as source_person_id, source_row_key, source_code,
           source_vocabulary_id, start_day, end_day
    from {{ ref('stg_b_visit') }}
), blood_pressure as (
    select hospital, person_id as source_person_id, source_row_key, source_code,
           source_vocabulary_id, bp_day, value, unit_vocabulary_id, unit_mapping_code,
           unit_source_value, value_source_value
    from {{ ref('stg_a_bp_value') }} where is_omop_bp
    union all
    select hospital, person_id as source_person_id, source_row_key, source_code,
           source_vocabulary_id, bp_day, value, unit_vocabulary_id, unit_mapping_code,
           unit_source_value, value_source_value
    from {{ ref('stg_b_bp_value') }} where is_omop_bp
), events as (
    select 'visit_occurrence'::varchar as omop_table, visit.hospital, visit.source_person_id,
           visit.source_row_key, visit.source_code, visit.start_day,
           coalesce(visit.end_day, visit.start_day) as end_day,
           coalesce(mapping.target_concept_id, 0)::integer as concept_id,
           null::numeric as value_as_number, null::integer as unit_concept_id,
           null::varchar as unit_source_value, null::varchar as value_source_value
    from visits visit
    left join {{ ref('source_to_concept_map') }} mapping
      on mapping.source_vocabulary_id = visit.source_vocabulary_id
     and mapping.source_code = visit.source_code
    union all
    select 'condition_occurrence'::varchar, hospital, source_person_id,
           source_row_key, source_code, start_day, end_day, concept_id,
           null::numeric, null::integer, null::varchar, null::varchar
    from {{ ref('omop_diagnoses') }} where concept_id > 0
    union all
    select 'measurement'::varchar, bp.hospital, bp.source_person_id,
           bp.source_row_key, bp.source_code, bp.bp_day, bp.bp_day,
           coalesce(mapping.target_concept_id, 0)::integer,
           cast(bp.value as numeric), coalesce(unit.target_concept_id, 0)::integer,
           bp.unit_source_value, bp.value_source_value
    from blood_pressure bp
    left join {{ ref('source_to_concept_map') }} mapping
      on mapping.source_vocabulary_id = bp.source_vocabulary_id
     and mapping.source_code = bp.source_code
    left join {{ ref('source_to_concept_map') }} unit
      on unit.source_vocabulary_id = bp.unit_vocabulary_id
     and unit.source_code = bp.unit_mapping_code
)
select omop_table,
       cast(row_number() over (partition by omop_table order by hospital, source_row_key) as integer) as omop_id,
       {{ omop_person_id('hospital', 'source_person_id') }} as person_id,
       hospital, source_row_key, source_code, start_day, end_day, concept_id,
       value_as_number, unit_concept_id, unit_source_value, value_source_value
from events
