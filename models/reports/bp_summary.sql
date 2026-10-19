-- D6,D7 / t01,t06,t09,Q3: summarize finished person results; retain an empty denominator date.
select dates.as_of,
       cast(count(person.person_id) as integer) as denominator,
       cast(coalesce(sum(person.controlled), 0) as integer) as numerator,
       cast(round(sum(person.controlled)::double / nullif(count(person.person_id), 0), 4) as double) as rate
from {{ ref('dim_as_of_dates') }} dates
left join {{ ref('fct_bp_person') }} person on person.as_of = dates.as_of
group by dates.as_of
