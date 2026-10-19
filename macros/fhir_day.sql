{# D1 / t14: use the written calendar date, without timezone conversion. L3 only. #}
{% macro fhir_day(expression) -%}
cast(substr({{ expression }}, 1, 10) as date)
{%- endmacro %}
