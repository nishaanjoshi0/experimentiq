with invalid_splits as (
    select
      experiment_id,
      sum(traffic_split) as total_traffic_split
    from {{ source('experimentiq_raw', 'variations') }}
    group by experiment_id
)

select
  experiment_id,
  total_traffic_split
from invalid_splits
where abs(total_traffic_split - 1.0) > 0.01
