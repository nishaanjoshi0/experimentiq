select *
from {{ source('experimentiq_raw', 'experiment_events') }}
where event_date > current_date()
