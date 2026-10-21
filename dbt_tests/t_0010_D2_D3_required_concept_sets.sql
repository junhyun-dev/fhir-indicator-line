-- D2,D3 / decision 0010: a misspelled or missing set must not silently remove patients.
with required as (
    select 'systolic'::varchar as concept_set
    union all select 'diastolic'::varchar
    union all select 'bp_unit'::varchar
    union all select 'essential_hypertension'::varchar
    union all select 'outpatient_visit'::varchar
    union all select 'inpatient_or_ed_visit'::varchar
)
select required.concept_set from required
where not exists (
    select 1 from {{ ref('indicator_concepts') }} concepts
    where concepts.concept_set = required.concept_set
)
