-- L0 / decisions 0004,0009; request 06 Q3: approved fixed provenance. Official CDM 5.4 column order and types.
{{ config(materialized='table') }}
select
       cast('fhir-indicator-line learning CDM' as varchar) as cdm_source_name,
       cast('FIL' as varchar) as cdm_source_abbreviation,
       cast('learning project' as varchar) as cdm_holder,
       cast(null as varchar) as source_description,
       cast(null as varchar) as source_documentation_reference,
       cast(null as varchar) as cdm_etl_reference,
       cast(date '2026-10-21' as date) as source_release_date,
       cast(date '2026-10-21' as date) as cdm_release_date,
       cast('5.4' as varchar) as cdm_version,
       cast(798878 as integer) as cdm_version_concept_id,
       cast('subset 2026-10-21 (dbt-synthea 33fdbfa)' as varchar) as vocabulary_version

