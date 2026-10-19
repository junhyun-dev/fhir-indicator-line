-- D1,D2,M2 / t06,t10,t11,t12,t14,Q3: A's calendar and age; eligibility stays in L5.
with patients as (
    select id as person_id,
           {{ fhir_day("json_extract_string(payload_json, '$.birthDate')") }} as birth_date
    from {{ source('fhir', 'latest_resources') }}
    where resource_type = 'Patient'
), periods as (
    select 'A'::varchar as hospital, labels.as_of_label, patients.person_id,
           make_date(2025, labels.month, labels.day) as as_of,
           date '2025-01-01' as measurement_start_day,
           date '2025-12-31' as measurement_end_day,
           date '2025-06-30' as hypertension_cutoff_day,
           2025 - year(patients.birth_date) as age_at_year_end
    from patients
    cross join {{ ref('as_of_labels') }} labels
)
select hospital, as_of_label, person_id, as_of,
       measurement_start_day, measurement_end_day,
       least(measurement_end_day, as_of) as period_end_day,
       hypertension_cutoff_day, age_at_year_end
from periods
