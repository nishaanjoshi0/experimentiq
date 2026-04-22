with event_counts as (
    select
      experiment_id,
      variation_id,
      count(distinct user_id) as user_count,
      count(*) as event_count
    from {{ ref('stg_experiment_events') }}
    group by experiment_id, variation_id
),
metric_rollup as (
    select
      experiment_id,
      variation_id,
      avg(value) as avg_metric_value,
      count(distinct user_id) as observed_user_count
    from {{ ref('stg_metric_observations') }}
    group by experiment_id, variation_id
)

select
  e.experiment_id,
  e.variation_id,
  e.user_count,
  e.event_count,
  m.avg_metric_value,
  safe_divide(m.observed_user_count, e.user_count) as conversion_rate
from event_counts as e
left join metric_rollup as m
  on e.experiment_id = m.experiment_id
 and e.variation_id = m.variation_id
