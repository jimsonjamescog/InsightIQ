select *
from {{ ref('data_quality_metrics') }}
where metric_date = to_date('2026-09-14')
  and field_name = 'customer_region'
  and round(null_rate, 3) <> 0.631
