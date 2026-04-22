select
  cast(observation_id as string) as observation_id,
  cast(experiment_id as string) as experiment_id,
  cast(variation_id as string) as variation_id,
  cast(user_id as string) as user_id,
  cast(metric_id as string) as metric_id,
  cast(value as float64) as value,
  cast(observation_date as date) as observation_date,
  cast(timestamp as timestamp) as timestamp
from {{ source('experimentiq_raw', 'metric_observations') }}
where value is not null
  and user_id is not null
  and cast(observation_date as date) <= current_date()
