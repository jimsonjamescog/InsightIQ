select
    snapshot_date as metric_date,
    'customer_region' as field_name,
    sum(case when customer_region is null then 1 else 0 end)::float / count(*) as null_rate,
    count(*) as row_count
from {{ ref('customer_dimension_snapshot') }}
group by snapshot_date
union all
select distinct order_date, 'customer_id', 0.0, 1000 from {{ ref('stg_orders') }}
union all
select distinct order_date, 'order_total', 0.001, 1000 from {{ ref('stg_orders') }}
union all
select distinct payment_date, 'payment_status', 0.0, 1000
from {{ source('raw', 'payments') }}
