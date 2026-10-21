-- D1-D3 / decision 0011: an exact source key for each carried event row.
{{ config(materialized='table') }}
select omop_table::varchar as omop_table, omop_id::integer as omop_id,
       hospital::varchar as hospital, source_row_key::varchar as source_row_key
from {{ ref('omop_event_rows') }}
