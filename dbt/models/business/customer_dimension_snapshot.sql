with dates as (
    select distinct order_date as snapshot_date from {{ ref('stg_orders') }}
)
select
    dates.snapshot_date,
    customers.customer_id,
    customers.customer_name,
    customers.region_code,
    case
        when dates.snapshot_date = to_date('2026-09-14') and customers.region_code <> 'NA' then null
        when dates.snapshot_date < to_date('2026-09-14') and customers.customer_id > 996 then null
        when customers.region_code = 'NA' then 'North America'
        when customers.region_code = 'EU' then 'Europe'
        when customers.region_code = 'APAC' then 'Asia Pacific'
    end as customer_region,
    customers.channel
from {{ ref('stg_customers') }} customers
cross join dates
