select
    customer_id,
    customer_name,
    region_code,
    channel,
    created_at
from {{ source('raw', 'customers') }}
