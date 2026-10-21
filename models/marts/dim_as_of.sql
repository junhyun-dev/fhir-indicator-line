-- D1,D6 / decisions 0004,0010: retain labels even with no eligible people.
select distinct hospital, as_of_label
from {{ ref('int_person_period') }}
