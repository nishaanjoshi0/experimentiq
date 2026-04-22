select
  cast(event_id as string) as event_id,
  cast(experiment_id as string) as experiment_id,
  cast(variation_id as string) as variation_id,
  cast(user_id as string) as user_id,
  cast(event_date as date) as event_date,
  cast(timestamp as timestamp) as timestamp,
  cast(platform as string) as platform,
  cast(country as string) as country
from {{ source('experimentiq_raw', 'experiment_events') }}
where user_id is not null
  and cast(event_date as date) <= current_date()
