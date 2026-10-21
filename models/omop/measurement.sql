-- D1,D3 / decisions 0004,0007-0009,0011. Official CDM 5.4 column order and types.
{{ config(materialized='table') }}
select
       cast(omop_id as integer) as measurement_id,
       cast(person_id as integer) as person_id,
       cast(concept_id as integer) as measurement_concept_id,
       cast(start_day as date) as measurement_date,
       cast(null as timestamp) as measurement_datetime,
       cast(null as varchar) as measurement_time,
       cast(32817 as integer) as measurement_type_concept_id,
       cast(null as integer) as operator_concept_id,
       cast(value_as_number as numeric) as value_as_number,
       cast(null as integer) as value_as_concept_id,
       cast(unit_concept_id as integer) as unit_concept_id,
       cast(null as numeric) as range_low,
       cast(null as numeric) as range_high,
       cast(null as integer) as provider_id,
       cast(null as integer) as visit_occurrence_id,
       cast(null as integer) as visit_detail_id,
       cast(source_code as varchar) as measurement_source_value,
       cast(null as integer) as measurement_source_concept_id,
       cast(unit_source_value as varchar) as unit_source_value,
       cast(null as integer) as unit_source_concept_id,
       cast(value_source_value as varchar) as value_source_value,
       cast(null as integer) as measurement_event_id,
       cast(null as integer) as meas_event_field_concept_id
from {{ ref('omop_event_rows') }} where omop_table = 'measurement'
