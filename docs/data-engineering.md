# DE1–DE3 implementation guide

This repository implements the three data-engineering roles as one testable vertical slice. The local DuckDB backend is the reference implementation; Snowflake uses the same logical schemas and tool contracts.

## DE1 — Data foundation

`insightiq.data.warehouse` creates 90 days of deterministic business history:

| Schema | Tables | Purpose |
|---|---|---|
| `raw` | customers, products, orders, order_items, web_traffic, payments | Source-level business records |
| `business` | customer_dimension_snapshot, fct_orders, daily_actual_revenue, daily_revenue, regional_revenue, daily_traffic, daily_payment_metrics | Tested analytical facts and KPIs |
| `quality` | data_quality_metrics | Historical field-level validation results |

The generator creates 1,000 customers, 60 products, 9,000 orders, and exactly 90 days of history. The validation step checks history depth, row counts, actual incident-day revenue, reported incident-day revenue, and the injected null rate.

The selected public source is UCI Online Retail II. `data/sources.yml` records its publisher, URL, DOI, license, and coverage. The optional `import-uci` command normalizes a downloaded workbook into `raw.public_online_retail`; the repository does not redistribute the source file.

Commands:

```bash
insightiq-data build --db data/insightiq.duckdb
insightiq-data validate --db data/insightiq.duckdb
insightiq-data profile --db data/insightiq.duckdb
insightiq-data import-uci --source data/source/online_retail_II.xlsx
```

Definition of done: `validate` returns `{"valid": true, "errors": []}` and SQL can independently establish the revenue movement.

## DE2 — Mystery and operational metadata

The controlled scenario is injected during transformation, not by altering the raw orders:

```text
deploy-284 changes customer-region mapping
  -> EU/APAC legacy region values map to NULL
  -> customer_region null rate rises from 0.4% to 63.1%
  -> the reporting model excludes null-region transactions
  -> actual revenue remains $120,000
  -> reported revenue falls to $72,000 (-40%)
```

Operational tables include deployments, pipeline runs, schema changes, data dependencies, incidents, and documents. Decoys include a checkout UI deployment, recommendation deployment, historical payment latency, stable payment failure rates, stable traffic, and successful pipeline runs.

Reset the entire mystery reproducibly:

```bash
insightiq-data reset
```

The scenario builder also provides the negative-test worlds:

| Scenario | Expected result |
|---|---|
| `missing_deployment` | Root cause not established |
| `conflicting_evidence` | Root cause not established; H4 is rejected with supporting and contradicting evidence |
| `payment_failure` | H2 is supported as the root cause |
| `data_quality_no_deployment` | Root cause not established |
| `insufficient_evidence` | Root cause not established |

Select one with `insightiq-data reset --scenario <name>`.

The evaluator alone reads `scenarios/ground_truth.json`. It is not loaded into DuckDB or Snowflake and is not registered as an agent tool.

## DE3 — Analytics and tooling

`insightiq.tools.warehouse` exposes these typed, allowlisted operations:

1. `get_kpi`
2. `compare_periods`
3. `decompose_kpi`
4. `segment_metric`
5. `detect_anomaly`
6. `check_data_quality`
7. `get_deployments`
8. `get_pipeline_runs`
9. `inspect_schema_changes`
10. `get_dependencies`
11. `search_incidents`
12. `calculate_business_impact`

Every execution returns:

```text
tool_name
execution_id
query_id
source
timestamp
result
error
```

Business impact accepts only the metric name. Current and expected values are read from the warehouse, preventing the model from supplying invented calculation inputs.

Each established causal link contains:

```text
link_id
sequence
statement
classification: OBSERVED | INFERRED
evidence_ids
```

The gate verifies every referenced evidence ID, blocks unresolved contradictions against the proposed hypothesis, and rejects incomplete causal sequences.

The model never receives unrestricted SQL. User-controlled metric and dimension names are Pydantic literals, database identifiers are selected from internal allowlists, and query provenance is recorded before evidence can be accepted.

## Snowflake deployment

1. Copy `.env.example` to `.env` and configure the Snowflake variables.
2. Install the optional connector: `pip install -e ".[snowflake]"`.
3. Run `insightiq-snowflake-load`. It executes `warehouse/snowflake/00_setup.sql`, generates the source world locally, and loads raw and operational tables.
4. Install `dbt-snowflake` in your preferred dbt environment.
5. Run `dbt build --profiles-dir dbt`.
6. Set `INSIGHTIQ_DATA_BACKEND=snowflake` before starting the API.

The dbt project contains staging models, the customer snapshot, order fact, KPI models, quality history, schema tests, relationship tests, and singular incident assertions.

## Verification

```bash
ruff check .
pytest --cov=insightiq --cov-report=term-missing
python -m insightiq.evaluation.runner
```

The warehouse integration test executes every DE3 tool against a newly built temporary database and then runs the complete investigator against it. The investigation regression suite runs the base mystery ten times and independently tests every negative scenario.
