-- D1,D2,M2 / t06,t10,t11,t12,Q3: union hospital calendars without eligibility filtering.
with hospital_rows as (
    select hospital, as_of_label, person_id, as_of,
           measurement_start_day, measurement_end_day, period_end_day,
           hypertension_cutoff_day, age_at_year_end
    from {{ ref('stg_a_person_period') }}
)
select * from hospital_rows
