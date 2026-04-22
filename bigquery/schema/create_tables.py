"""Create ExperimentIQ BigQuery dataset and core tables."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from schema_definitions import (
    EXPERIMENT_EVENTS_SCHEMA,
    EXPERIMENTS_SCHEMA,
    METRICS_SCHEMA,
    METRIC_OBSERVATIONS_SCHEMA,
    VARIATIONS_SCHEMA,
)


DEFAULT_DATASET = "experimentation"
DEFAULT_LOCATION = "US"


def configure_logging() -> None:
    """Configure application logging for the table creation script."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def load_environment() -> tuple[str, str]:
    """Load local environment variables and return the configured project and dataset."""
    load_dotenv()

    project_id = (
        os.getenv("BIGQUERY_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCLOUD_PROJECT")
    )
    if not project_id:
        raise ValueError("BIGQUERY_PROJECT_ID must be set in the environment or .env file.")

    dataset_id = os.getenv("BIGQUERY_DATASET", DEFAULT_DATASET)
    return project_id, dataset_id


def create_dataset(client: bigquery.Client, dataset_ref: str) -> None:
    """Create the target BigQuery dataset if it does not already exist."""
    try:
        client.get_dataset(dataset_ref)
        logging.info("Skipped existing dataset: %s", dataset_ref)
        return
    except NotFound:
        pass

    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = DEFAULT_LOCATION
    client.create_dataset(dataset, exists_ok=True)
    logging.info("Created dataset: %s", dataset_ref)


def build_table(
    table_id: str,
    schema: list[bigquery.SchemaField],
    partition_field: str | None = None,
    clustering_fields: list[str] | None = None,
) -> bigquery.Table:
    """Build a BigQuery table definition with optional partitioning and clustering."""
    table = bigquery.Table(table_id, schema=schema)

    if partition_field:
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field=partition_field,
        )

    if clustering_fields:
        table.clustering_fields = clustering_fields

    return table


def create_table(client: bigquery.Client, table: bigquery.Table) -> None:
    """Create a BigQuery table and log whether it was created or skipped."""
    try:
        client.get_table(table.reference)
        logging.info("Skipped existing table: %s", table.table_id)
        return
    except NotFound:
        pass

    client.create_table(table, exists_ok=True)
    logging.info("Created table: %s", table.table_id)


def create_tables(client: bigquery.Client, dataset_ref: str) -> None:
    """Create all ExperimentIQ core tables for the configured dataset."""
    clustering_fields = ["experiment_id", "variation_id"]
    tables = [
        build_table(f"{dataset_ref}.experiments", EXPERIMENTS_SCHEMA),
        build_table(f"{dataset_ref}.variations", VARIATIONS_SCHEMA),
        build_table(
            f"{dataset_ref}.experiment_events",
            EXPERIMENT_EVENTS_SCHEMA,
            partition_field="event_date",
            clustering_fields=clustering_fields,
        ),
        build_table(f"{dataset_ref}.metrics", METRICS_SCHEMA),
        build_table(
            f"{dataset_ref}.metric_observations",
            METRIC_OBSERVATIONS_SCHEMA,
            partition_field="observation_date",
            clustering_fields=clustering_fields,
        ),
    ]

    for table in tables:
        create_table(client, table)


def main() -> None:
    """Run the standalone dataset and table creation workflow."""
    configure_logging()
    project_id, dataset_id = load_environment()
    client = bigquery.Client(project=project_id)
    dataset_ref = f"{project_id}.{dataset_id}"

    create_dataset(client, dataset_ref)
    create_tables(client, dataset_ref)


if __name__ == "__main__":
    main()
