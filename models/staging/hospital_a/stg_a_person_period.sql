-- D1,D2 / decisions 0005,0010: retain A's calendar and expose original demographics.
with patients as (
    select id as person_id,
           nullif(json_extract_string(payload_json, '$.gender'), '') as gender_source_value,
           {{ fhir_day("json_extract_string(payload_json, '$.birthDate')") }} as birth_date
    from {{ source('fhir', 'latest_resources') }}
    where resource_type = 'Patient'
), periods as (
    select 'A'::varchar as hospital, labels.as_of_label, patients.person_id,
           make_date(2025, labels.month, labels.day) as as_of,
           date '2025-01-01' as measurement_start_day,
           date '2025-12-31' as measurement_end_day,
           date '2025-06-30' as hypertension_cutoff_day,
           2025 - year(patients.birth_date) as age_at_year_end,
           year(patients.birth_date)::integer as year_of_birth,
           patients.gender_source_value
    from patients
    cross join {{ ref('as_of_labels') }} labels
)
select hospital, as_of_label, person_id, as_of,
       measurement_start_day, measurement_end_day,
       least(measurement_end_day, as_of) as period_end_day,
       hypertension_cutoff_day, age_at_year_end,
       year_of_birth, gender_source_value, 2025::integer as measurement_year,
       'hospital_a_gender'::varchar as gender_vocabulary_id
from periods
