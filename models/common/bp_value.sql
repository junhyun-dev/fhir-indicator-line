-- D1,D3,M2 / t08,t13: map hospital/code/unit; preserve each value and ignore code system.
with hospital_rows as (
    select hospital, observation_id, person_id, source_code, value, source_unit, bp_day, record_day
    from {{ ref('stg_a_bp_value') }}
    union all
    select hospital, observation_id, person_id, source_code, value, source_unit, bp_day, record_day
    from {{ ref('stg_b_bp_value') }}
)
select bp.hospital, bp.observation_id, bp.person_id, bp.source_code, mapping.concept,
       bp.value, mapping.std_unit, bp.bp_day, bp.record_day
from hospital_rows bp
join {{ ref('code_map') }} mapping
  on mapping.hospital = bp.hospital and mapping.source_code = bp.source_code
 and mapping.source_unit = bp.source_unit
where mapping.concept in ('systolic', 'diastolic')
