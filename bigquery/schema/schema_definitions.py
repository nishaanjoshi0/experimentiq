"""BigQuery schema definitions for ExperimentIQ tables."""

from google.cloud.bigquery import SchemaField


EXPERIMENTS_SCHEMA = [
    SchemaField("experiment_id", "STRING", mode="REQUIRED", description="Primary key, UUID"),
    SchemaField("name", "STRING", mode="REQUIRED", description="Human-readable experiment name"),
    SchemaField("hypothesis", "STRING", mode="REQUIRED", description="Full hypothesis statement"),
    SchemaField("status", "STRING", mode="REQUIRED", description="draft / running / completed / abandoned"),
    SchemaField("primary_metric", "STRING", mode="REQUIRED", description="The one metric this experiment is optimizing"),
    SchemaField("guardrail_metrics", "JSON", mode="NULLABLE", description="Array of metric names that must not degrade"),
    SchemaField("owner_id", "STRING", mode="REQUIRED", description="Hashed user ID of experiment owner"),
    SchemaField("created_at", "TIMESTAMP", mode="REQUIRED", description="Creation time"),
    SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED", description="Last update time"),
    SchemaField("started_at", "TIMESTAMP", mode="NULLABLE", description="When experiment started running"),
    SchemaField("ended_at", "TIMESTAMP", mode="NULLABLE", description="When experiment concluded"),
]

VARIATIONS_SCHEMA = [
    SchemaField("variation_id", "STRING", mode="REQUIRED", description="Primary key, UUID"),
    SchemaField("experiment_id", "STRING", mode="REQUIRED", description="Foreign key to experiments"),
    SchemaField("name", "STRING", mode="REQUIRED", description='e.g. "control", "treatment_a"'),
    SchemaField("type", "STRING", mode="REQUIRED", description="control / treatment"),
    SchemaField("traffic_split", "FLOAT", mode="REQUIRED", description="Proportion of traffic, e.g. 0.5"),
]

EXPERIMENT_EVENTS_SCHEMA = [
    SchemaField("event_id", "STRING", mode="REQUIRED", description="Primary key, UUID"),
    SchemaField("experiment_id", "STRING", mode="REQUIRED", description="Foreign key to experiments"),
    SchemaField("variation_id", "STRING", mode="REQUIRED", description="Foreign key to variations"),
    SchemaField("user_id", "STRING", mode="REQUIRED", description="Hashed/anonymized user identifier — never PII"),
    SchemaField("event_date", "DATE", mode="REQUIRED", description="Partition column"),
    SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED", description="Full event timestamp"),
    SchemaField("platform", "STRING", mode="NULLABLE", description="web / ios / android"),
    SchemaField("country", "STRING", mode="NULLABLE", description="ISO country code"),
]

METRICS_SCHEMA = [
    SchemaField("metric_id", "STRING", mode="REQUIRED", description="Primary key, UUID"),
    SchemaField("experiment_id", "STRING", mode="REQUIRED", description="Foreign key to experiments"),
    SchemaField("metric_name", "STRING", mode="REQUIRED", description='e.g. "checkout_conversion", "revenue_per_user"'),
    SchemaField("metric_type", "STRING", mode="REQUIRED", description="conversion / revenue / engagement / guardrail"),
    SchemaField("numerator_column", "STRING", mode="REQUIRED", description="Column in metric_observations for numerator"),
    SchemaField("denominator_column", "STRING", mode="NULLABLE", description="Column for denominator (for ratio metrics)"),
    SchemaField("higher_is_better", "BOOLEAN", mode="REQUIRED", description="Direction of improvement"),
]

METRIC_OBSERVATIONS_SCHEMA = [
    SchemaField("observation_id", "STRING", mode="REQUIRED", description="Primary key, UUID"),
    SchemaField("experiment_id", "STRING", mode="REQUIRED", description="Foreign key to experiments"),
    SchemaField("variation_id", "STRING", mode="REQUIRED", description="Foreign key to variations"),
    SchemaField("user_id", "STRING", mode="REQUIRED", description="Hashed/anonymized user identifier"),
    SchemaField("metric_id", "STRING", mode="REQUIRED", description="Foreign key to metrics"),
    SchemaField("value", "FLOAT", mode="REQUIRED", description="Observed metric value"),
    SchemaField("observation_date", "DATE", mode="REQUIRED", description="Partition column"),
    SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED", description="Full observation timestamp"),
]
