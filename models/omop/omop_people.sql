-- D2 / decisions 0005,0007,0009,0010: one original person, independent of as-of labels. ADR0013: derived source union only.
{{ config(materialized='table') }}
with demographics as (
    select hospital, person_id as source_person_id, year_of_birth,
           measurement_year, gender_source_value, gender_vocabulary_id
    from {{ ref('stg_a_person') }}
    union all
    select hospital, person_id as source_person_id, year_of_birth,
           measurement_year, gender_source_value, gender_vocabulary_id
    from {{ ref('stg_b_person') }}
    union all
    select hospital, person_id as source_person_id, year_of_birth,
           measurement_year, gender_source_value, gender_vocabulary_id
    from {{ ref('stg_aprime_person') }}
)
select {{ omop_person_id('p.hospital', 'p.source_person_id') }} as person_id,
       p.hospital, p.source_person_id, p.year_of_birth::integer as year_of_birth,
       p.measurement_year::integer as measurement_year, p.gender_source_value,
       coalesce(mapping.target_concept_id, 0)::integer as gender_concept_id
from demographics p
left join {{ ref('source_to_concept_map') }} mapping
  on mapping.source_vocabulary_id = p.gender_vocabulary_id
 and mapping.source_code = p.gender_source_value
