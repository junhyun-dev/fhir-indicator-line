-- D1 / decisions 0004,0011; request 06 Q2: include carried event ends. Official CDM 5.4 column order and types.
{{ config(materialized='table') }}
select
       cast(person_id as integer) as observation_period_id,
       cast(person_id as integer) as person_id,
       cast(min(start_day) as date) as observation_period_start_date,
       cast(max(coalesce(end_day, start_day)) as date) as observation_period_end_date,
       cast(32817 as integer) as period_type_concept_id
from {{ ref('omop_event_rows') }} group by person_id
