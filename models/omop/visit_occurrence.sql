-- D1-D3 / decisions 0004,0007,0009,0011. Official CDM 5.4 column order and types.
{{ config(materialized='table') }}
select
       cast(omop_id as integer) as visit_occurrence_id,
       cast(person_id as integer) as person_id,
       cast(concept_id as integer) as visit_concept_id,
       cast(start_day as date) as visit_start_date,
       cast(null as timestamp) as visit_start_datetime,
       cast(end_day as date) as visit_end_date,
       cast(null as timestamp) as visit_end_datetime,
       cast(32817 as integer) as visit_type_concept_id,
       cast(null as integer) as provider_id,
       cast(null as integer) as care_site_id,
       cast(source_code as varchar) as visit_source_value,
       cast(null as integer) as visit_source_concept_id,
       cast(null as integer) as admitted_from_concept_id,
       cast(null as varchar) as admitted_from_source_value,
       cast(null as integer) as discharged_to_concept_id,
       cast(null as varchar) as discharged_to_source_value,
       cast(null as integer) as preceding_visit_occurrence_id
from {{ ref('omop_event_rows') }} where omop_table = 'visit_occurrence'
