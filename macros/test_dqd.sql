{# D1-D3 / ADR0004,0008,0009,0011: DQD-inspired counts, not the complete DQD runner.
   Thresholds are percentages in schema.yml; compare before rounding, with strict >.
   The result contains aggregate counts only, never patient identifiers.
#}
{% macro dqd_rate(model, violation, eligible, threshold) %}
with counts as (
    select count(*) filter (where {{ eligible }}) as denominator,
           count(*) filter (where ({{ eligible }}) and ({{ violation }})) as violation_count
    from {{ model }} as dqd_row
)
select violation_count, denominator,
       100.0 * violation_count / nullif(denominator, 0) as violation_percent
from counts
where violation_count * 100.0 > {{ threshold }} * denominator
{% endmacro %}

{% test dqd_value_completeness(model, column_name, threshold) %}
{{ dqd_rate(model, column_name ~ ' is null', 'true', threshold) }}
{% endtest %}

{% test dqd_concept_completeness(model, column_name, threshold, source_column=none) %}
{% set eligible = column_name ~ ' is not null' %}
{% set violation = column_name ~ ' = 0' %}
{% if source_column %}
    {% set eligible = '(' ~ eligible ~ ' or ' ~ source_column ~ ' is not null)' %}
    {% set violation = '(' ~ violation ~ ' or (' ~ column_name ~ ' is null and ' ~ source_column ~ ' is not null))' %}
{% endif %}
{{ dqd_rate(model, violation, eligible, threshold) }}
{% endtest %}

{% test dqd_fk_domain(model, column_name, to, domain, threshold) %}
{% set violation %}
not exists (select 1 from {{ to }} c
            where c.concept_id = dqd_row.{{ column_name }} and c.domain_id = '{{ domain }}')
{% endset %}
{# Includes a missing concept, rather than allowing an inner join to hide it. #}
{{ dqd_rate(model, violation, column_name ~ ' is not null and ' ~ column_name ~ ' <> 0', threshold) }}
{% endtest %}

{% test dqd_standard_valid(model, column_name, to, threshold) %}
{% set violation %}
exists (select 1 from {{ to }} c where c.concept_id = dqd_row.{{ column_name }}
        and (c.standard_concept is distinct from 'S' or c.invalid_reason is not null))
{% endset %}
{# Missing FK is covered separately by the existing relationships test. #}
{{ dqd_rate(model, violation, column_name ~ ' is not null and ' ~ column_name ~ ' <> 0', threshold) }}
{% endtest %}

{% test dqd_value_low(model, column_name, minimum, threshold) %}
{{ dqd_rate(model, column_name ~ ' < ' ~ minimum, column_name ~ ' is not null', threshold) }}
{% endtest %}

{% test dqd_date_order(model, start_column, end_column, threshold) %}
{{ dqd_rate(model, start_column ~ ' > ' ~ end_column,
            start_column ~ ' is not null and ' ~ end_column ~ ' is not null', threshold) }}
{% endtest %}

{% test dqd_unit_plausibility(model, concept_ids, allowed_units, threshold) %}
{# DQD evaluates each measurement concept separately; pooling can hide one failing concept. #}
with counts as (
    select measurement_concept_id,
           count(*) filter (where unit_concept_id <> 0 or unit_concept_id is null) as denominator,
           count(*) filter (where unit_concept_id is not null
                           and unit_concept_id not in (0, {{ allowed_units | join(',') }})) as violation_count
    from {{ model }}
    where measurement_concept_id in ({{ concept_ids | join(',') }})
    group by measurement_concept_id
)
select measurement_concept_id, violation_count, denominator,
       100.0 * violation_count / nullif(denominator, 0) as violation_percent
from counts
where violation_count * 100.0 > {{ threshold }} * denominator
{% endtest %}

{% test dqd_unmapped_diagnoses(model, threshold) %}
{# D1 / ADR0009: project-specific counts, not a DQD built-in or mapping coverage %. #}
select hospital, not_carried
from {{ model }}
where omop_table = 'condition_occurrence' and not_carried > {{ threshold }}
{% endtest %}
