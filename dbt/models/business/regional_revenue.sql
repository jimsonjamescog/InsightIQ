select order_date as metric_date, customer_region as region,
       sum(order_total)::float as revenue, count(*) as orders
from {{ ref('fct_orders') }}
where order_status = 'PAID' and customer_region is not null
group by order_date, customer_region
