select *
from {{ ref('daily_revenue') }}
where metric_date = to_date('2026-09-14')
  and revenue <> 72000
