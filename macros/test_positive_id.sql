{# D2 / decision 0007: a zero remainder must fail instead of changing the ID algorithm. #}
{% test positive_id(model, column_name) %}
select {{ column_name }} from {{ model }} where {{ column_name }} <= 0
{% endtest %}
