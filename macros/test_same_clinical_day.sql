{# D1 / decision 0006: late or missing clinical dates must stop the real build. #}
{% test same_clinical_day(model, clinical_column) %}
{{ config(tags=['record_day']) }}
select * from {{ model }}
where record_day is distinct from {{ clinical_column }}
   or record_day is null or {{ clinical_column }} is null
{% endtest %}
