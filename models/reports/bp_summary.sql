-- D6,D7,M2 / t01,t06,t09,Q3: summarize by hospital/label, retaining empty denominators.
select periods.hospital, periods.as_of_label,
       cast(count(person.person_id) as integer) as denominator,
       cast(coalesce(sum(person.controlled), 0) as integer) as numerator,
       cast(round(sum(person.controlled)::double / nullif(count(person.person_id), 0), 4) as double) as rate
from {{ ref('dim_as_of') }} periods
left join {{ ref('fct_bp_person') }} person
  on person.hospital = periods.hospital and person.as_of_label = periods.as_of_label
group by periods.hospital, periods.as_of_label
