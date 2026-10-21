{# D2 / decisions 0005,0007: hash the original person key before narrowing to INTEGER. #}
{% macro omop_person_id(hospital, source_id) -%}
cast(md5_number({{ hospital }} || ':' || {{ source_id }}) % 2147483647 as integer)
{%- endmacro %}
