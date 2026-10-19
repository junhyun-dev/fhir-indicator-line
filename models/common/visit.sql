-- D1,D2,D3,M2 / t07,t09,t12: union visits carrying the hospital's interpreted visit type.
with hospital_rows as (
    select hospital, visit_id, person_id, visit_type, start_day, end_day, record_day
    from {{ ref('stg_a_visit') }}
    union all
    select hospital, visit_id, person_id, visit_type, start_day, end_day, record_day
    from {{ ref('stg_b_visit') }}
)
select * from hospital_rows
