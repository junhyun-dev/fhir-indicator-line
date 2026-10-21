-- D1,D2 / decisions 0004,0007,0009,0011. Official CDM 5.4 column order and types.
{{ config(materialized='table') }}
select
       cast(omop_id as integer) as condition_occurrence_id,
       cast(person_id as integer) as person_id,
       cast(concept_id as integer) as condition_concept_id,
       cast(start_day as date) as condition_start_date,
       cast(null as timestamp) as condition_start_datetime,
       cast(end_day as date) as condition_end_date,
       cast(null as timestamp) as condition_end_datetime,
       cast(32817 as integer) as condition_type_concept_id,
       cast(null as integer) as condition_status_concept_id,
       cast(null as varchar) as stop_reason,
       cast(null as integer) as provider_id,
       cast(null as integer) as visit_occurrence_id,
       cast(null as integer) as visit_detail_id,
       cast(source_code as varchar) as condition_source_value,
       cast(null as integer) as condition_source_concept_id,
       cast(null as varchar) as condition_status_source_value
from {{ ref('omop_event_rows') }} where omop_table = 'condition_occurrence'
