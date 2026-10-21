-- D1,D2 / decisions 0001,0005,0010: the sole indicator calendar and age calculation.
with calendar as (
    select ext.hospital, labels.as_of_label,
           person.person_source_value::varchar as person_id,
           person.person_id::integer as omop_person_id,
           make_date(ext.measurement_year, labels.month, labels.day) as as_of,
           make_date(ext.measurement_year, 1, 1) as measurement_start_day,
           make_date(ext.measurement_year, 12, 31) as measurement_end_day,
           make_date(ext.measurement_year, 6, 30) as hypertension_cutoff_day,
           (ext.measurement_year - person.year_of_birth)::integer as age_at_year_end
    from {{ ref('person') }} person
    join {{ ref('person_ext') }} ext using (person_id)
    cross join {{ ref('as_of_labels') }} labels
)
select hospital, as_of_label, person_id, as_of, measurement_start_day, measurement_end_day,
       least(measurement_end_day, as_of) as period_end_day,
       hypertension_cutoff_day, age_at_year_end, omop_person_id
from calendar
