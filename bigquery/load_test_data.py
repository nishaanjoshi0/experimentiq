"""Load realistic ExperimentIQ test data into BigQuery."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from google.cloud import bigquery


DEFAULT_PROJECT_ID: Final[str] = os.getenv("BIGQUERY_PROJECT_ID", "")
DEFAULT_DATASET: Final[str] = "experimentation"
DEFAULT_SERVICE_ACCOUNT_PATH: Final[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
OWNER_EMAIL: Final[str] = os.getenv("OWNER_EMAIL", "owner@example.com")
INSERT_BATCH_SIZE: Final[int] = 500
RANDOM_SEED: Final[int] = 42


@dataclass(frozen=True)
class MetricConfig:
    """Metric definition and synthetic generation settings."""

    name: str
    metric_type: str
    higher_is_better: bool
    control_rate: float | None = None
    treatment_rate: float | None = None
    control_mean: float | None = None
    control_std: float | None = None
    treatment_mean: float | None = None
    treatment_std: float | None = None


@dataclass(frozen=True)
class ExperimentConfig:
    """High-level configuration for a synthetic experiment."""

    number: int
    experiment_id: str
    name: str
    hypothesis: str
    status: str
    primary_metric: str
    guardrail_metrics: list[str]
    started_days_ago: int
    ended_days_ago: int | None
    control_users: int
    treatment_users: int
    platform_distribution: list[tuple[str, float]]
    country_distribution: list[tuple[str, float]]
    primary_metric_config: MetricConfig
    guardrail_metric_configs: list[MetricConfig]


def configure_logging() -> None:
    """Configure logging for the loader script."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def load_environment() -> tuple[str, str, str]:
    """Load environment variables and return project, dataset, and credentials path."""
    script_dir = Path(__file__).resolve().parent
    load_dotenv()
    load_dotenv(script_dir / ".env")
    load_dotenv(script_dir / "schema" / ".env")

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", DEFAULT_SERVICE_ACCOUNT_PATH)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    project_id = os.getenv("BIGQUERY_PROJECT_ID", DEFAULT_PROJECT_ID)
    dataset = os.getenv("BIGQUERY_DATASET", DEFAULT_DATASET)
    return project_id, dataset, credentials_path


def create_client(project_id: str) -> bigquery.Client:
    """Create a BigQuery client for the configured project."""
    return bigquery.Client(project=project_id)


def hash_sha256(value: str) -> str:
    """Return a SHA-256 hash for a string value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def to_timestamp_string(value: datetime) -> str:
    """Convert a timezone-aware datetime to an RFC3339 UTC timestamp string."""
    return value.astimezone(timezone.utc).isoformat()


def to_date_string(value: datetime) -> str:
    """Convert a datetime to an ISO date string."""
    return value.date().isoformat()


def random_timestamp_between(start: datetime, end: datetime, rng: random.Random) -> datetime:
    """Return a random UTC timestamp between two UTC datetimes."""
    start_ts = start.timestamp()
    end_ts = end.timestamp()
    sampled = rng.uniform(start_ts, end_ts)
    return datetime.fromtimestamp(sampled, tz=timezone.utc)


def clamp_positive(value: float) -> float:
    """Clamp a numeric value to a small positive minimum."""
    return max(value, 0.01)


def weighted_choice(distribution: list[tuple[str, float]], rng: random.Random) -> str:
    """Choose a label from a weighted distribution."""
    labels = [label for label, _ in distribution]
    weights = [weight for _, weight in distribution]
    return rng.choices(labels, weights=weights, k=1)[0]


def chunk_rows(rows: list[dict], chunk_size: int) -> list[list[dict]]:
    """Split a row list into insertable chunks."""
    return [rows[index:index + chunk_size] for index in range(0, len(rows), chunk_size)]


def insert_rows(client: bigquery.Client, table_id: str, rows: list[dict]) -> None:
    """Load rows into a BigQuery table using batch load."""
    if not rows:
        logging.info("No rows to insert for %s", table_id)
        return

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )

    chunk_size = 1000
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        job = client.load_table_from_json(chunk, table_id, job_config=job_config)
        job.result()
        logging.info("Loaded %d rows into %s (chunk %d)", len(chunk), table_id, i // chunk_size + 1)


def build_experiment_configs() -> list[ExperimentConfig]:
    """Return the six configured realistic experiments."""
    return [
        ExperimentConfig(
            number=1,
            experiment_id="exp_checkout_button_001",
            name="Checkout Button Color Test",
            hypothesis="Changing the checkout button from grey to green will increase checkout conversion rate",
            status="completed",
            primary_metric="checkout_conversion_rate",
            guardrail_metrics=["revenue_per_user", "cart_abandonment_rate"],
            started_days_ago=14,
            ended_days_ago=1,
            control_users=4500,
            treatment_users=4500,
            platform_distribution=[("web", 0.6), ("ios", 0.3), ("android", 0.1)],
            country_distribution=[("US", 0.7), ("UK", 0.15), ("CA", 0.1), ("AU", 0.05)],
            primary_metric_config=MetricConfig(
                name="checkout_conversion_rate",
                metric_type="conversion",
                higher_is_better=True,
                control_rate=0.12,
                treatment_rate=0.145,
            ),
            guardrail_metric_configs=[
                MetricConfig(
                    name="revenue_per_user",
                    metric_type="guardrail",
                    higher_is_better=True,
                    control_mean=85.0,
                    control_std=30.0,
                    treatment_mean=87.0,
                    treatment_std=31.0,
                ),
                MetricConfig(
                    name="cart_abandonment_rate",
                    metric_type="guardrail",
                    higher_is_better=False,
                    control_rate=0.18,
                    treatment_rate=0.175,
                ),
            ],
        ),
        ExperimentConfig(
            number=2,
            experiment_id="exp_onboarding_email_002",
            name="Onboarding Email Sequence Length Test",
            hypothesis="A 5-email onboarding sequence will increase 7-day activation rate compared to the current 3-email sequence",
            status="completed",
            primary_metric="d7_activation_rate",
            guardrail_metrics=["email_unsubscribe_rate", "support_ticket_rate"],
            started_days_ago=21,
            ended_days_ago=7,
            control_users=4250,
            treatment_users=4250,
            platform_distribution=[("web", 1.0)],
            country_distribution=[("US", 0.65), ("UK", 0.2), ("OTHER", 0.15)],
            primary_metric_config=MetricConfig(
                name="d7_activation_rate",
                metric_type="conversion",
                higher_is_better=True,
                control_rate=0.30,
                treatment_rate=0.31,
            ),
            guardrail_metric_configs=[
                MetricConfig(
                    name="email_unsubscribe_rate",
                    metric_type="guardrail",
                    higher_is_better=False,
                    control_rate=0.018,
                    treatment_rate=0.021,
                ),
                MetricConfig(
                    name="support_ticket_rate",
                    metric_type="guardrail",
                    higher_is_better=False,
                    control_rate=0.010,
                    treatment_rate=0.011,
                ),
            ],
        ),
        ExperimentConfig(
            number=3,
            experiment_id="exp_pricing_layout_003",
            name="Pricing Page Layout Test",
            hypothesis="A three-column pricing layout will increase plan upgrade rate compared to the current two-column layout",
            status="running",
            primary_metric="plan_upgrade_rate",
            guardrail_metrics=["page_exit_rate", "support_ticket_rate"],
            started_days_ago=5,
            ended_days_ago=None,
            control_users=4800,
            treatment_users=3200,
            platform_distribution=[("web", 0.7), ("ios", 0.2), ("android", 0.1)],
            country_distribution=[("US", 0.65), ("UK", 0.2), ("OTHER", 0.15)],
            primary_metric_config=MetricConfig(
                name="plan_upgrade_rate",
                metric_type="conversion",
                higher_is_better=True,
                control_rate=0.08,
                treatment_rate=0.083,
            ),
            guardrail_metric_configs=[
                MetricConfig(
                    name="page_exit_rate",
                    metric_type="guardrail",
                    higher_is_better=False,
                    control_rate=0.24,
                    treatment_rate=0.241,
                ),
                MetricConfig(
                    name="support_ticket_rate",
                    metric_type="guardrail",
                    higher_is_better=False,
                    control_rate=0.012,
                    treatment_rate=0.013,
                ),
            ],
        ),
        ExperimentConfig(
            number=4,
            experiment_id="exp_search_autocomplete_004",
            name="Search Autocomplete Feature Test",
            hypothesis="Adding autocomplete to the search bar will increase search-to-click rate",
            status="running",
            primary_metric="search_to_click_rate",
            guardrail_metrics=["page_load_time_p95", "search_abandonment_rate"],
            started_days_ago=3,
            ended_days_ago=None,
            control_users=4100,
            treatment_users=4100,
            platform_distribution=[("web", 0.5), ("ios", 0.35), ("android", 0.15)],
            country_distribution=[("US", 0.6), ("UK", 0.25), ("OTHER", 0.15)],
            primary_metric_config=MetricConfig(
                name="search_to_click_rate",
                metric_type="conversion",
                higher_is_better=True,
                control_rate=0.34,
                treatment_rate=0.36,
            ),
            guardrail_metric_configs=[
                MetricConfig(
                    name="page_load_time_p95",
                    metric_type="guardrail",
                    higher_is_better=False,
                    control_mean=1.82,
                    control_std=0.18,
                    treatment_mean=1.88,
                    treatment_std=0.19,
                ),
                MetricConfig(
                    name="search_abandonment_rate",
                    metric_type="guardrail",
                    higher_is_better=False,
                    control_rate=0.22,
                    treatment_rate=0.215,
                ),
            ],
        ),
        ExperimentConfig(
            number=5,
            experiment_id="exp_trial_length_005",
            name="Free Trial Length Test",
            hypothesis="Extending free trial from 7 days to 14 days will increase paid conversion rate",
            status="completed",
            primary_metric="paid_conversion_rate",
            guardrail_metrics=["revenue_per_user", "trial_completion_rate"],
            started_days_ago=30,
            ended_days_ago=2,
            control_users=5000,
            treatment_users=5000,
            platform_distribution=[("web", 0.55), ("ios", 0.3), ("android", 0.15)],
            country_distribution=[("US", 0.7), ("UK", 0.15), ("OTHER", 0.15)],
            primary_metric_config=MetricConfig(
                name="paid_conversion_rate",
                metric_type="conversion",
                higher_is_better=True,
                control_rate=0.09,
                treatment_rate=0.11,
            ),
            guardrail_metric_configs=[
                MetricConfig(
                    name="revenue_per_user",
                    metric_type="guardrail",
                    higher_is_better=True,
                    control_mean=95.0,
                    control_std=34.0,
                    treatment_mean=72.0,
                    treatment_std=28.0,
                ),
                MetricConfig(
                    name="trial_completion_rate",
                    metric_type="guardrail",
                    higher_is_better=True,
                    control_rate=0.62,
                    treatment_rate=0.54,
                ),
            ],
        ),
        ExperimentConfig(
            number=6,
            experiment_id="exp_mobile_checkout_006",
            name="Mobile Checkout Simplification Test",
            hypothesis="Simplifying mobile checkout from 4 steps to 2 steps will increase mobile checkout completion rate",
            status="completed",
            primary_metric="checkout_completion_rate",
            guardrail_metrics=["payment_error_rate", "order_accuracy_rate"],
            started_days_ago=20,
            ended_days_ago=3,
            control_users=4750,
            treatment_users=4750,
            platform_distribution=[("ios", 0.6), ("android", 0.4)],
            country_distribution=[("US", 0.65), ("UK", 0.2), ("OTHER", 0.15)],
            primary_metric_config=MetricConfig(
                name="checkout_completion_rate",
                metric_type="conversion",
                higher_is_better=True,
                control_rate=0.18,
                treatment_rate=0.26,
            ),
            guardrail_metric_configs=[
                MetricConfig(
                    name="payment_error_rate",
                    metric_type="guardrail",
                    higher_is_better=False,
                    control_rate=0.016,
                    treatment_rate=0.014,
                ),
                MetricConfig(
                    name="order_accuracy_rate",
                    metric_type="guardrail",
                    higher_is_better=True,
                    control_rate=0.985,
                    treatment_rate=0.987,
                ),
            ],
        ),
    ]


def build_metric_rows(
    config: ExperimentConfig,
    metric_ids: dict[str, str],
) -> list[dict]:
    """Build metric definition rows for an experiment."""
    rows: list[dict] = []
    all_metrics = [config.primary_metric_config, *config.guardrail_metric_configs]
    for metric in all_metrics:
        rows.append(
            {
                "metric_id": metric_ids[metric.name],
                "experiment_id": config.experiment_id,
                "metric_name": metric.name,
                "metric_type": metric.metric_type,
                "numerator_column": "value",
                "denominator_column": None,
                "higher_is_better": metric.higher_is_better,
            }
        )
    return rows


def build_variation_rows(config: ExperimentConfig, variation_ids: dict[str, str]) -> list[dict]:
    """Build variation rows for an experiment."""
    total_users = config.control_users + config.treatment_users
    return [
        {
            "variation_id": variation_ids["control"],
            "experiment_id": config.experiment_id,
            "name": "control",
            "type": "control",
            "traffic_split": config.control_users / total_users,
        },
        {
            "variation_id": variation_ids["treatment"],
            "experiment_id": config.experiment_id,
            "name": "treatment",
            "type": "treatment",
            "traffic_split": config.treatment_users / total_users,
        },
    ]


def choose_user_indexes(total_users: int, count: int, rng: random.Random) -> set[int]:
    """Choose a reproducible set of user indexes for an outcome."""
    return set(rng.sample(range(total_users), count))


def build_event_rows_and_user_context(
    config: ExperimentConfig,
    variation_ids: dict[str, str],
    rng: random.Random,
) -> tuple[list[dict], dict[str, dict]]:
    """Build experiment event rows and a user context lookup."""
    now = utc_now()
    started_at = now - timedelta(days=config.started_days_ago)
    ended_at = now - timedelta(days=config.ended_days_ago) if config.ended_days_ago is not None else now
    user_context: dict[str, dict] = {}
    event_rows: list[dict] = []

    variation_plan = [
        ("control", config.control_users),
        ("treatment", config.treatment_users),
    ]

    for variation_name, user_count in variation_plan:
        for index in range(user_count):
            global_index = len(user_context)
            user_id = hash_sha256(f"user_exp{config.number}_{global_index}")
            event_timestamp = random_timestamp_between(started_at, ended_at, rng)
            platform = weighted_choice(config.platform_distribution, rng)
            country = weighted_choice(config.country_distribution, rng)
            variation_id = variation_ids[variation_name]

            user_context[user_id] = {
                "variation_name": variation_name,
                "variation_id": variation_id,
                "timestamp": event_timestamp,
                "event_date": to_date_string(event_timestamp),
            }

            event_rows.append(
                {
                    "event_id": str(uuid.uuid4()),
                    "experiment_id": config.experiment_id,
                    "variation_id": variation_id,
                    "user_id": user_id,
                    "event_date": to_date_string(event_timestamp),
                    "timestamp": to_timestamp_string(event_timestamp),
                    "platform": platform,
                    "country": country,
                }
            )

    return event_rows, user_context


def sample_normal_observation(mean: float, stddev: float, rng: random.Random) -> float:
    """Sample a positive normal observation."""
    return round(clamp_positive(rng.gauss(mean, stddev)), 2)


def build_binary_metric_observations(
    experiment_id: str,
    metric_id: str,
    user_ids: list[str],
    user_context: dict[str, dict],
    metric_value: float = 1.0,
) -> list[dict]:
    """Build metric observation rows for binary metrics."""
    rows: list[dict] = []
    for user_id in user_ids:
        context = user_context[user_id]
        rows.append(
            {
                "observation_id": str(uuid.uuid4()),
                "experiment_id": experiment_id,
                "variation_id": context["variation_id"],
                "user_id": user_id,
                "metric_id": metric_id,
                "value": metric_value,
                "observation_date": context["event_date"],
                "timestamp": to_timestamp_string(context["timestamp"] + timedelta(minutes=5)),
            }
        )
    return rows


def build_value_metric_observations(
    experiment_id: str,
    metric_id: str,
    user_ids: list[str],
    user_context: dict[str, dict],
    mean: float,
    stddev: float,
    rng: random.Random,
) -> list[dict]:
    """Build metric observation rows for value metrics."""
    rows: list[dict] = []
    for user_id in user_ids:
        context = user_context[user_id]
        rows.append(
            {
                "observation_id": str(uuid.uuid4()),
                "experiment_id": experiment_id,
                "variation_id": context["variation_id"],
                "user_id": user_id,
                "metric_id": metric_id,
                "value": sample_normal_observation(mean, stddev, rng),
                "observation_date": context["event_date"],
                "timestamp": to_timestamp_string(context["timestamp"] + timedelta(minutes=10)),
            }
        )
    return rows


def build_metric_observations(
    config: ExperimentConfig,
    metric_ids: dict[str, str],
    user_context: dict[str, dict],
    rng: random.Random,
) -> list[dict]:
    """Build realistic metric observation rows for an experiment."""
    control_user_ids = [user_id for user_id, ctx in user_context.items() if ctx["variation_name"] == "control"]
    treatment_user_ids = [user_id for user_id, ctx in user_context.items() if ctx["variation_name"] == "treatment"]
    observations: list[dict] = []

    primary_control_count = round(config.primary_metric_config.control_rate * len(control_user_ids))
    primary_treatment_count = round(config.primary_metric_config.treatment_rate * len(treatment_user_ids))
    primary_control_indexes = choose_user_indexes(len(control_user_ids), primary_control_count, rng)
    primary_treatment_indexes = choose_user_indexes(len(treatment_user_ids), primary_treatment_count, rng)
    primary_control_users = [control_user_ids[index] for index in sorted(primary_control_indexes)]
    primary_treatment_users = [treatment_user_ids[index] for index in sorted(primary_treatment_indexes)]
    converted_users = {
        "control": primary_control_users,
        "treatment": primary_treatment_users,
    }

    observations.extend(
        build_binary_metric_observations(
            config.experiment_id,
            metric_ids[config.primary_metric_config.name],
            primary_control_users + primary_treatment_users,
            user_context,
        )
    )

    for metric in config.guardrail_metric_configs:
        metric_id = metric_ids[metric.name]
        if metric.control_mean is not None and metric.treatment_mean is not None:
            observations.extend(
                build_value_metric_observations(
                    config.experiment_id,
                    metric_id,
                    converted_users["control"],
                    user_context,
                    metric.control_mean,
                    metric.control_std or 1.0,
                    rng,
                )
            )
            observations.extend(
                build_value_metric_observations(
                    config.experiment_id,
                    metric_id,
                    converted_users["treatment"],
                    user_context,
                    metric.treatment_mean,
                    metric.treatment_std or 1.0,
                    rng,
                )
            )
            continue

        if metric.name == "order_accuracy_rate":
            control_count = round((metric.control_rate or 0.0) * len(converted_users["control"]))
            treatment_count = round((metric.treatment_rate or 0.0) * len(converted_users["treatment"]))
            control_indexes = choose_user_indexes(len(converted_users["control"]), control_count, rng)
            treatment_indexes = choose_user_indexes(len(converted_users["treatment"]), treatment_count, rng)
            metric_control_users = [converted_users["control"][index] for index in sorted(control_indexes)]
            metric_treatment_users = [converted_users["treatment"][index] for index in sorted(treatment_indexes)]
        else:
            control_count = round((metric.control_rate or 0.0) * len(control_user_ids))
            treatment_count = round((metric.treatment_rate or 0.0) * len(treatment_user_ids))
            control_indexes = choose_user_indexes(len(control_user_ids), control_count, rng)
            treatment_indexes = choose_user_indexes(len(treatment_user_ids), treatment_count, rng)
            metric_control_users = [control_user_ids[index] for index in sorted(control_indexes)]
            metric_treatment_users = [treatment_user_ids[index] for index in sorted(treatment_indexes)]

        if metric.name == "page_load_time_p95":
            observations.extend(
                build_value_metric_observations(
                    config.experiment_id,
                    metric_id,
                    converted_users["control"],
                    user_context,
                    metric.control_mean or 1.0,
                    metric.control_std or 0.1,
                    rng,
                )
            )
            observations.extend(
                build_value_metric_observations(
                    config.experiment_id,
                    metric_id,
                    converted_users["treatment"],
                    user_context,
                    metric.treatment_mean or 1.0,
                    metric.treatment_std or 0.1,
                    rng,
                )
            )
            continue

        observations.extend(
            build_binary_metric_observations(
                config.experiment_id,
                metric_id,
                metric_control_users + metric_treatment_users,
                user_context,
            )
        )

    return observations


def build_experiment_row(config: ExperimentConfig, owner_id: str) -> dict:
    """Build an experiment metadata row."""
    now = utc_now()
    started_at = now - timedelta(days=config.started_days_ago)
    ended_at = now - timedelta(days=config.ended_days_ago) if config.ended_days_ago is not None else None
    created_at = started_at - timedelta(days=7)
    updated_at = ended_at or now

    return {
        "experiment_id": config.experiment_id,
        "name": config.name,
        "hypothesis": config.hypothesis,
        "status": config.status,
        "primary_metric": config.primary_metric,
        "guardrail_metrics": config.guardrail_metrics,
        "owner_id": owner_id,
        "created_at": to_timestamp_string(created_at),
        "updated_at": to_timestamp_string(updated_at),
        "started_at": to_timestamp_string(started_at),
        "ended_at": to_timestamp_string(ended_at) if ended_at is not None else None,
    }


def build_rows() -> dict[str, list[dict]]:
    """Build all rows for experiments, variations, events, metrics, and metric observations."""
    rng = random.Random(RANDOM_SEED)
    owner_id = hash_sha256(OWNER_EMAIL)
    experiment_rows: list[dict] = []
    variation_rows: list[dict] = []
    event_rows: list[dict] = []
    metric_rows: list[dict] = []
    metric_observation_rows: list[dict] = []

    for config in build_experiment_configs():
        experiment_rows.append(build_experiment_row(config, owner_id))
        variation_ids = {
            "control": str(uuid.uuid4()),
            "treatment": str(uuid.uuid4()),
        }
        metric_ids = {
            metric.name: str(uuid.uuid4())
            for metric in [config.primary_metric_config, *config.guardrail_metric_configs]
        }

        variation_rows.extend(build_variation_rows(config, variation_ids))
        metric_rows.extend(build_metric_rows(config, metric_ids))
        experiment_event_rows, user_context = build_event_rows_and_user_context(config, variation_ids, rng)
        event_rows.extend(experiment_event_rows)
        metric_observation_rows.extend(build_metric_observations(config, metric_ids, user_context, rng))

    return {
        "experiments": experiment_rows,
        "variations": variation_rows,
        "experiment_events": event_rows,
        "metrics": metric_rows,
        "metric_observations": metric_observation_rows,
    }


def main() -> None:
    """Load realistic ExperimentIQ experiments into BigQuery."""
    configure_logging()
    project_id, dataset, credentials_path = load_environment()
    logging.info("Using credentials from %s", credentials_path)
    client = create_client(project_id)
    rows = build_rows()
    table_prefix = f"{project_id}.{dataset}"

    logging.info(
        "Prepared row counts: %s",
        json.dumps({table: len(table_rows) for table, table_rows in rows.items()}, sort_keys=True),
    )
    insert_rows(client, f"{table_prefix}.experiments", rows["experiments"])
    insert_rows(client, f"{table_prefix}.variations", rows["variations"])
    insert_rows(client, f"{table_prefix}.experiment_events", rows["experiment_events"])
    insert_rows(client, f"{table_prefix}.metrics", rows["metrics"])
    insert_rows(client, f"{table_prefix}.metric_observations", rows["metric_observations"])
    logging.info("Finished loading six realistic experiments into %s.%s", project_id, dataset)


if __name__ == "__main__":
    main()
