-- D2 / decisions 0005,0010: keep hospital and measurement year beside the official person.
{{ config(materialized='table') }}
select person_id::integer as person_id, hospital::varchar as hospital,
       measurement_year::integer as measurement_year
from {{ ref('omop_people') }}
