-- D1,D6,M2 / Q3: retain labels even when the hospital has no eligible people.
select distinct hospital, as_of_label
from {{ ref('person_period') }}
