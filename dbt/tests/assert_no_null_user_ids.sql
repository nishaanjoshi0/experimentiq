select *
from {{ source('experimentiq_raw', 'experiment_events') }}
where user_id is null
