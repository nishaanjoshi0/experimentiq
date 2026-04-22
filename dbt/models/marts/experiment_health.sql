with latest_events as (
    select
      experiment_id,
      max(event_date) as latest_event_date
    from {{ ref('stg_experiment_events') }}
    group by experiment_id
),
summary as (
    select
      experiment_id,
      total_users,
      variation_count
    from {{ ref('experiment_summary') }}
),
health_flags as (
    select
      s.experiment_id,
      s.total_users,
      s.variation_count,
      s.total_users >= 100 as has_minimum_sample,
      l.latest_event_date >= date_sub(current_date(), interval 1 day) as is_data_fresh,
      s.variation_count >= 2 as has_multiple_variations
    from summary as s
    left join latest_events as l
      on s.experiment_id = l.experiment_id
),
scored as (
    select
      experiment_id,
      total_users,
      variation_count,
      has_minimum_sample,
      is_data_fresh,
      has_multiple_variations,
      cast(not has_minimum_sample as int64)
      + cast(not is_data_fresh as int64)
      + cast(not has_multiple_variations as int64) as failed_checks
    from health_flags
)

select
  experiment_id,
  total_users,
  variation_count,
  has_minimum_sample,
  is_data_fresh,
  has_multiple_variations,
  case
    when failed_checks = 0 then 'healthy'
    when failed_checks = 1 then 'warning'
    else 'critical'
  end as health_status
from scored
