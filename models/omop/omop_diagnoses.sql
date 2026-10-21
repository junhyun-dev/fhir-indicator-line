-- D1,D2 / decisions 0006,0009,0011: preserve every source diagnosis for omission counts.
{{ config(materialized='table') }}
with diagnoses as (
    select hospital, person_id as source_person_id, condition_id as source_row_key,
           source_code, source_vocabulary_id, start_day, end_day
    from {{ ref('stg_a_condition') }}
    union all
    select hospital, person_id as source_person_id, source_row_key,
           source_code, source_vocabulary_id, start_day, end_day
    from {{ ref('stg_b_diagnosis') }}
)
select diagnosis.*,
       coalesce(mapping.target_concept_id, 0)::integer as concept_id
from diagnoses diagnosis
left join {{ ref('source_to_concept_map') }} mapping
  on mapping.source_vocabulary_id = diagnosis.source_vocabulary_id
 and mapping.source_code = diagnosis.source_code
