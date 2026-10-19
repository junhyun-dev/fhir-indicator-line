-- D1,D6 / t10-t12,Q3: carry all requested dates to L6, including dates with no eligible person.
select as_of
from {{ ref('stg_as_of_dates') }}
