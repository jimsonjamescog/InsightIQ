select
    orders.order_id,
    orders.customer_id,
    orders.order_date,
    orders.ordered_at,
    orders.channel,
    orders.order_status,
    orders.order_total,
    customers.customer_region,
    products.category as product_category
from {{ ref('stg_orders') }} orders
join {{ ref('customer_dimension_snapshot') }} customers
  on customers.customer_id = orders.customer_id
 and customers.snapshot_date = orders.order_date
join {{ source('raw', 'order_items') }} items on items.order_id = orders.order_id
join {{ source('raw', 'products') }} products on products.product_id = items.product_id
