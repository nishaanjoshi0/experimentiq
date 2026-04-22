with event_rollup as (
    select
      experiment_id,
      count(distinct user_id) as total_users,
      count(*) as total_events,
      min(event_date) as start_date,
      max(event_date) as end_date,
      date_diff(max(event_date), min(event_date), day) as days_running,
      count(distinct variation_id) as variation_count
    from {{ ref('stg_experiment_events') }}
    group by experiment_id
)

select
  experiment_id,
  total_users,
  total_events,
  start_date,
  end_date,
  days_running,
  variation_count
from event_rollup
