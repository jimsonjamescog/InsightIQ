select
    payment_date as metric_date,
    sum(case when status = 'FAILED' then 1 else 0 end)::float / count(*) as payment_failure_rate,
    count(*) as payment_attempts
from {{ source('raw', 'payments') }}
group by payment_date
