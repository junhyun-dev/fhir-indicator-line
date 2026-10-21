-- D1,D2 / decisions 0005,0010: retain B's calendar and original demographics.
{{ config(materialized='table') }}
with people as (
    select subject_id as person_id,
           cast(anchor_year as integer) as anchor_year,
           cast(anchor_age as integer) as age_at_year_end,
           nullif(gender, '') as gender_source_value
    from {{ source('mimic', 'patients') }}
), periods as (
    select 'B'::varchar as hospital, labels.as_of_label, people.person_id,
           make_date(people.anchor_year, labels.month, labels.day) as as_of,
           make_date(people.anchor_year, 1, 1) as measurement_start_day,
           make_date(people.anchor_year, 12, 31) as measurement_end_day,
           make_date(people.anchor_year, 6, 30) as hypertension_cutoff_day,
           people.age_at_year_end, people.anchor_year as measurement_year,
           people.anchor_year - people.age_at_year_end as year_of_birth,
           people.gender_source_value
    from people
    cross join {{ ref('as_of_labels') }} labels
)
select hospital, as_of_label, person_id, as_of,
       measurement_start_day, measurement_end_day,
       least(measurement_end_day, as_of) as period_end_day,
       hypertension_cutoff_day, age_at_year_end,
       year_of_birth, gender_source_value, measurement_year,
       'hospital_b_gender'::varchar as gender_vocabulary_id
from periods
