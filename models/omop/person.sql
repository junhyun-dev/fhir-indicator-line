-- D2 / decisions 0004,0005,0007,0009,0010. Official CDM 5.4 column order and types.
{{ config(materialized='table') }}
select
       cast(person_id as integer) as person_id,
       cast(gender_concept_id as integer) as gender_concept_id,
       cast(year_of_birth as integer) as year_of_birth,
       cast(null as integer) as month_of_birth,
       cast(null as integer) as day_of_birth,
       cast(null as timestamp) as birth_datetime,
       cast(0 as integer) as race_concept_id,
       cast(0 as integer) as ethnicity_concept_id,
       cast(null as integer) as location_id,
       cast(null as integer) as provider_id,
       cast(null as integer) as care_site_id,
       cast(source_person_id as varchar) as person_source_value,
       cast(gender_source_value as varchar) as gender_source_value,
       cast(null as integer) as gender_source_concept_id,
       cast(null as varchar) as race_source_value,
       cast(null as integer) as race_source_concept_id,
       cast(null as varchar) as ethnicity_source_value,
       cast(null as integer) as ethnicity_source_concept_id
from {{ ref('omop_people') }}
