select traffic_date as metric_date, sessions::float as traffic
from {{ source('raw', 'web_traffic') }}
