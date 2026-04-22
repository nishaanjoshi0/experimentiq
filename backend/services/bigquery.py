"""Async BigQuery service wrapper for ExperimentIQ."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date
from functools import partial
from typing import Any, Final

from google.cloud import bigquery


BIGQUERY_PROJECT_ID_ENV_VAR: Final[str] = "BIGQUERY_PROJECT_ID"
BIGQUERY_DATASET_ENV_VAR: Final[str] = "BIGQUERY_DATASET"
LOGGER_NAME: Final[str] = "experimentiq.bigquery"
MISSING_CONFIG_MESSAGE: Final[str] = "BIGQUERY_PROJECT_ID and BIGQUERY_DATASET must be set."
EXPERIMENT_EVENTS_TABLE: Final[str] = "experiment_events"
METRIC_OBSERVATIONS_TABLE: Final[str] = "metric_observations"
EXPERIMENT_HEALTH_TABLE: Final[str] = "experiment_health"
NOT_FOUND_RESULT: Final[None] = None

EXPERIMENT_EVENTS_QUERY: Final[str] = """
select
  user_id,
  variation_id,
  event_date,
  timestamp,
  platform,
  country
from `{table_name}`
where experiment_id = @experiment_id
  and (@start_date is null or event_date >= @start_date)
  and (@end_date is null or event_date <= @end_date)
order by event_date, timestamp
"""

METRIC_OBSERVATIONS_QUERY: Final[str] = """
select
  user_id,
  variation_id,
  metric_id,
  value,
  timestamp
from `{table_name}`
where experiment_id = @experiment_id
  and (@metric_id is null or metric_id = @metric_id)
order by timestamp
"""

VARIATION_USER_COUNTS_QUERY: Final[str] = """
select
  variation_id,
  count(distinct user_id) as user_count
from `{table_name}`
where experiment_id = @experiment_id
group by variation_id
"""

EXPERIMENT_HEALTH_QUERY: Final[str] = """
select
  experiment_id,
  total_users,
  variation_count,
  has_minimum_sample,
  is_data_fresh,
  has_multiple_variations,
  health_status
from `{table_name}`
where experiment_id = @experiment_id
limit 1
"""

PRE_EXPERIMENT_METRIC_QUERY: Final[str] = """
with experiment_start as (
  select
    min(event_date) as start_date
  from `{events_table_name}`
  where experiment_id = @experiment_id
),
experiment_users as (
  select distinct user_id
  from `{events_table_name}`
  where experiment_id = @experiment_id
)
select
  mo.user_id,
  avg(mo.value) as pre_value
from `{metrics_table_name}` as mo
cross join experiment_start as es
inner join experiment_users as eu
  on mo.user_id = eu.user_id
where mo.experiment_id = @experiment_id
  and mo.metric_id = @metric_id
  and es.start_date is not null
  and mo.timestamp >= timestamp(date_sub(es.start_date, interval @days_before day))
  and mo.timestamp < timestamp(es.start_date)
group by mo.user_id
order by mo.user_id
"""

DAILY_METRIC_RATES_QUERY: Final[str] = """
with daily_events as (
  select
    variation_id,
    event_date as observation_date,
    count(distinct user_id) as exposed_users
  from `{experiment_events_table}`
  where experiment_id = @experiment_id
  group by variation_id, observation_date
),
daily_metrics as (
  select
    variation_id,
    observation_date,
    count(distinct user_id) as converted_users
  from `{metric_observations_table}`
  where experiment_id = @experiment_id
    and (@metric_id is null or metric_id = @metric_id)
  group by variation_id, observation_date
)
select
  e.variation_id,
  e.observation_date,
  safe_divide(m.converted_users, e.exposed_users) as daily_rate
from daily_events e
left join daily_metrics m
  on e.variation_id = m.variation_id
 and e.observation_date = m.observation_date
order by e.variation_id, e.observation_date
"""

_bigquery_service: BigQueryService | None = None


class BigQueryServiceError(Exception):
    """Raised when a BigQuery service operation fails."""

    def __init__(self, message: str) -> None:
        """Initialize the service error with a message."""
        super().__init__(message)
        self.message = message


class BigQueryService:
    """Async wrapper around the Google BigQuery client."""

    def __init__(self) -> None:
        """Initialize the BigQuery service from environment configuration."""
        project_id = os.getenv(BIGQUERY_PROJECT_ID_ENV_VAR)
        dataset = os.getenv(BIGQUERY_DATASET_ENV_VAR)
        if not project_id or not dataset:
            raise ValueError(MISSING_CONFIG_MESSAGE)

        self._project_id = project_id
        self._dataset = dataset
        self._client = bigquery.Client(project=project_id)
        self._logger = logging.getLogger(LOGGER_NAME)

    async def get_experiment_events(
        self,
        experiment_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return experiment event rows for the requested experiment and date range."""
        parameters = [
            bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        ]
        return await self._run_query(
            query_name="get_experiment_events",
            query=EXPERIMENT_EVENTS_QUERY.format(table_name=self._table_name(EXPERIMENT_EVENTS_TABLE)),
            parameters=parameters,
        )

    async def get_metric_observations(
        self,
        experiment_id: str,
        metric_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return metric observation rows for the requested experiment and metric filter."""
        parameters = [
            bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
            bigquery.ScalarQueryParameter("metric_id", "STRING", metric_id),
        ]
        return await self._run_query(
            query_name="get_metric_observations",
            query=METRIC_OBSERVATIONS_QUERY.format(table_name=self._table_name(METRIC_OBSERVATIONS_TABLE)),
            parameters=parameters,
        )

    async def get_variation_user_counts(self, experiment_id: str) -> dict[str, int]:
        """Return distinct user counts keyed by variation identifier."""
        parameters = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id)]
        rows = await self._run_query(
            query_name="get_variation_user_counts",
            query=VARIATION_USER_COUNTS_QUERY.format(table_name=self._table_name(EXPERIMENT_EVENTS_TABLE)),
            parameters=parameters,
        )
        return {str(row["variation_id"]): int(row["user_count"]) for row in rows}

    async def get_variation_types(self, experiment_id: str) -> dict[str, str]:
        """Return a dict mapping variation_id to type ('control' or 'treatment')."""
        query = """
        SELECT variation_id, type
        FROM `{table}`
        WHERE experiment_id = @experiment_id
        """.format(table=self._table_name("variations"))
        parameters = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id)]
        rows = await self._run_query("get_variation_types", query, parameters)
        return {str(row["variation_id"]): str(row["type"]) for row in rows}

    async def get_experiment_health(self, experiment_id: str) -> dict[str, Any] | None:
        """Return the experiment health mart row for the requested experiment."""
        parameters = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id)]
        rows = await self._run_query(
            query_name="get_experiment_health",
            query=EXPERIMENT_HEALTH_QUERY.format(table_name=self._table_name(EXPERIMENT_HEALTH_TABLE)),
            parameters=parameters,
        )
        if not rows:
            return NOT_FOUND_RESULT
        return rows[0]

    async def get_pre_experiment_metric(
        self,
        experiment_id: str,
        metric_id: str,
        days_before: int = 7,
    ) -> list[dict[str, Any]]:
        """Return per-user pre-experiment metric values for CUPED-style adjustment."""
        parameters = [
            bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
            bigquery.ScalarQueryParameter("metric_id", "STRING", metric_id),
            bigquery.ScalarQueryParameter("days_before", "INT64", days_before),
        ]
        return await self._run_query(
            query_name="get_pre_experiment_metric",
            query=PRE_EXPERIMENT_METRIC_QUERY.format(
                events_table_name=self._table_name(EXPERIMENT_EVENTS_TABLE),
                metrics_table_name=self._table_name(METRIC_OBSERVATIONS_TABLE),
            ),
            parameters=parameters,
        )

    async def get_primary_metric_id(self, experiment_id: str) -> str | None:
        """Return the primary metric ID for an experiment from the metrics table."""
        query = """
        SELECT metric_id
        FROM `{table}`
        WHERE experiment_id = @experiment_id
        AND metric_type = 'conversion'
        ORDER BY metric_id
        LIMIT 1
        """.format(table=self._table_name("metrics"))
        parameters = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id)]
        rows = await self._run_query("get_primary_metric_id", query, parameters)
        if rows:
            return str(rows[0]["metric_id"])
        return None

    async def get_guardrail_metrics(self, experiment_id: str) -> list[dict[str, Any]]:
        """Return all guardrail metric definitions for an experiment."""
        query = """
        SELECT metric_id, metric_name, metric_type, higher_is_better
        FROM `{table}`
        WHERE experiment_id = @experiment_id
        AND metric_type = 'guardrail'
        """.format(table=self._table_name("metrics"))
        parameters = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id)]
        return await self._run_query("get_guardrail_metrics", query, parameters)

    async def get_guardrail_metric_results(
        self,
        experiment_id: str,
        guardrail_metric_ids: list[str],
        control_id: str,
        treatment_id: str,
        variation_counts: dict[str, int],
    ) -> list[dict[str, Any]]:
        """Compute control vs treatment stats for each guardrail metric."""
        if not guardrail_metric_ids:
            return []

        guardrail_metrics = await self.get_guardrail_metrics(experiment_id)
        metric_map = {
            str(metric["metric_id"]): metric
            for metric in guardrail_metrics
            if metric.get("metric_id") is not None
        }
        results: list[dict[str, Any]] = []
        control_total = variation_counts.get(control_id, 0)
        treatment_total = variation_counts.get(treatment_id, 0)

        for metric_id in guardrail_metric_ids:
            observations = await self.get_metric_observations(experiment_id, metric_id=metric_id)
            control_converters = sum(
                1 for row in observations if str(row.get("variation_id")) == control_id and row.get("user_id") is not None
            )
            treatment_converters = sum(
                1
                for row in observations
                if str(row.get("variation_id")) == treatment_id and row.get("user_id") is not None
            )
            control_rate = control_converters / control_total if control_total > 0 else 0.0
            treatment_rate = treatment_converters / treatment_total if treatment_total > 0 else 0.0
            relative_change = (
                (treatment_rate - control_rate) / control_rate if control_rate > 0 else 0.0
            )
            metric_definition = metric_map.get(metric_id, {})
            higher_is_better = bool(metric_definition.get("higher_is_better", True))
            degraded = treatment_rate < control_rate if higher_is_better else treatment_rate > control_rate
            results.append(
                {
                    "metric_id": metric_id,
                    "metric_name": str(metric_definition.get("metric_name", metric_id)),
                    "control_rate": control_rate,
                    "treatment_rate": treatment_rate,
                    "relative_change": relative_change,
                    "degraded": degraded,
                }
            )

        return results

    async def get_daily_metric_rates(
        self,
        experiment_id: str,
        metric_id: str | None = None,
    ) -> dict[str, list[float]]:
        """Return daily conversion rates ordered by day for each variation."""
        parameters = [
            bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
            bigquery.ScalarQueryParameter("metric_id", "STRING", metric_id),
        ]
        rows = await self._run_query(
            query_name="get_daily_metric_rates",
            query=DAILY_METRIC_RATES_QUERY.format(
                experiment_events_table=self._table_name(EXPERIMENT_EVENTS_TABLE),
                metric_observations_table=self._table_name(METRIC_OBSERVATIONS_TABLE),
            ),
            parameters=parameters,
        )
        if not rows:
            return {}

        grouped: dict[str, list[float]] = {}
        for row in rows:
            variation_id = str(row["variation_id"])
            daily_rate = float(row["daily_rate"] or 0.0)
            grouped.setdefault(variation_id, []).append(daily_rate)
        return grouped

    async def _run_query(
        self,
        query_name: str,
        query: str,
        parameters: list[bigquery.ScalarQueryParameter],
    ) -> list[dict[str, Any]]:
        """Execute a parameterized query asynchronously and return rows as dictionaries."""
        job_config = bigquery.QueryJobConfig(query_parameters=parameters)
        loop = asyncio.get_running_loop()
        started_at = time.perf_counter()

        try:
            rows = await loop.run_in_executor(
                None,
                partial(self._execute_query, query=query, job_config=job_config),
            )
        except Exception as error:
            raise BigQueryServiceError(f"BigQuery query failed for {query_name}.") from error

        latency_ms = (time.perf_counter() - started_at) * 1000
        self._logger.debug(
            "BigQuery query completed",
            extra={"query_name": query_name, "latency_ms": round(latency_ms, 2)},
        )
        return rows

    def _execute_query(
        self,
        query: str,
        job_config: bigquery.QueryJobConfig,
    ) -> list[dict[str, Any]]:
        """Execute a synchronous BigQuery query and materialize the results."""
        query_job = self._client.query(query, job_config=job_config)
        return [dict(row.items()) for row in query_job.result()]

    def _table_name(self, table_name: str) -> str:
        """Return the fully qualified BigQuery table name for the configured dataset."""
        return ".".join((self._project_id, self._dataset, table_name))


def get_bigquery_service() -> BigQueryService:
    """Return a singleton BigQuery service instance."""
    global _bigquery_service
    if _bigquery_service is None:
        _bigquery_service = BigQueryService()
    return _bigquery_service
