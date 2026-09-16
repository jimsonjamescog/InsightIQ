select
    order_id,
    customer_id,
    order_date,
    ordered_at,
    channel,
    order_status,
    order_total
from {{ source('raw', 'orders') }}
