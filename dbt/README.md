# ExperimentIQ dbt Project

This dbt project models ExperimentIQ experiment event and metric data in BigQuery.

## Setup

1. Copy `profiles.yml.example` to `~/.dbt/profiles.yml`.
2. Set the required environment variables:
   - `BIGQUERY_PROJECT_ID`
   - `BIGQUERY_DATASET`
   - `GOOGLE_APPLICATION_CREDENTIALS`
3. From the `dbt/` directory, install packages:

```bash
dbt deps
```

## Run Models

```bash
dbt run
```

## Run Tests

```bash
dbt test
```
