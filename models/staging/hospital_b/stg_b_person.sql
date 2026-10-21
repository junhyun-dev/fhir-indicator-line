-- D1,D2 / decisions 0002,0005,0010: one shifted person; preserve source demographics.
{{ config(materialized='table') }}
select 'B'::varchar as hospital, subject_id::varchar as person_id,
       cast(anchor_year as integer) - cast(anchor_age as integer) as year_of_birth,
       nullif(gender, '') as gender_source_value,
       cast(anchor_year as integer) as measurement_year,
       'hospital_b_gender'::varchar as gender_vocabulary_id
from {{ source('mimic', 'patients') }}
