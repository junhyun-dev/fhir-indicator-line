-- D1-D3 / decision 0009: count the official output independently of load-count metadata.
with reported as (
    select * from {{ ref('omop_load_counts') }}
)
select * from reported counts
where counts.carried <> case counts.omop_table
{% for table in ['person','observation_period','visit_occurrence','condition_occurrence','measurement'] %}
    when '{{ table }}' then (
        select count(*) from {{ ref(table) }} event
        join {{ ref('person_ext') }} ext using (person_id)
        where ext.hospital = counts.hospital
    )
{% endfor %}
    when 'person_ext' then (select count(*) from {{ ref('person_ext') }} ext where ext.hospital = counts.hospital)
    when 'cdm_source' then (select count(*) from {{ ref('cdm_source') }})
    else -1 end
