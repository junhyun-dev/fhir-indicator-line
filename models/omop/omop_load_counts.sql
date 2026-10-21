-- D1-D3 / decisions 0004,0009,0011: actual carried rows and explicit unmapped diagnoses.
{{ config(materialized='table') }}
with carried as (
    select hospital, 'person'::varchar as omop_table, count(*)::integer as carried
    from {{ ref('person') }} person
    join {{ ref('person_ext') }} ext using (person_id) group by hospital
    union all
    select hospital, 'person_ext'::varchar, count(*)::integer
    from {{ ref('person_ext') }} group by hospital
    union all
    select ext.hospital, 'observation_period'::varchar, count(*)::integer
    from {{ ref('observation_period') }} period
    join {{ ref('person_ext') }} ext using (person_id) group by ext.hospital
    union all
    select ext.hospital, 'visit_occurrence'::varchar, count(*)::integer
    from {{ ref('visit_occurrence') }} event
    join {{ ref('person_ext') }} ext using (person_id) group by ext.hospital
    union all
    select ext.hospital, 'condition_occurrence'::varchar, count(*)::integer
    from {{ ref('condition_occurrence') }} event
    join {{ ref('person_ext') }} ext using (person_id) group by ext.hospital
    union all
    select ext.hospital, 'measurement'::varchar, count(*)::integer
    from {{ ref('measurement') }} event
    join {{ ref('person_ext') }} ext using (person_id) group by ext.hospital
), omitted as (
    select hospital, count(*)::integer as not_carried
    from {{ ref('omop_diagnoses') }} where concept_id = 0 group by hospital
), hospitals as (
    select distinct hospital from {{ ref('person_ext') }}
), table_names as (
    select 'person'::varchar as omop_table
    union all select 'person_ext'::varchar
    union all select 'observation_period'::varchar
    union all select 'visit_occurrence'::varchar
    union all select 'condition_occurrence'::varchar
    union all select 'measurement'::varchar
), requested as (
    select hospitals.hospital, table_names.omop_table
    from hospitals cross join table_names
)
select requested.hospital, requested.omop_table, coalesce(carried.carried, 0)::integer as carried,
       case when requested.omop_table = 'condition_occurrence'
            then coalesce(omitted.not_carried, 0) else 0 end::integer as not_carried
from requested left join carried using (hospital, omop_table)
left join omitted using (hospital)
union all
select 'AB'::varchar, 'cdm_source'::varchar, count(*)::integer, 0::integer
from {{ ref('cdm_source') }}
