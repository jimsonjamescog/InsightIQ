select order_date as metric_date, sum(order_total)::float as revenue, count(*) as orders
from {{ ref('fct_orders') }}
where order_status = 'PAID'
group by order_date
