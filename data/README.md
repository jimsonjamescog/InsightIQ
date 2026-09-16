# InsightIQ data layer

The committed source is a deterministic generator rather than a large binary dataset. It creates 90 days of business history, raw operational tables, analytical models, quality metrics, and a controlled incident in a local DuckDB warehouse.

Build or reset the warehouse:

```bash
insightiq-data build
insightiq-data reset
insightiq-data validate
insightiq-data profile
```

The default output is `data/insightiq.duckdb`, which is ignored by Git. The FastAPI application automatically creates it when `INSIGHTIQ_DATA_BACKEND=duckdb` and the file is missing.

The generated source tables mirror the Snowflake schemas under `warehouse/snowflake`. Hidden ground truth is deliberately stored outside the warehouse in `scenarios/ground_truth.json`.

## Optional real-world source

The selected public source is [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail), recorded in `sources.yml`. Download the workbook from UCI, then run:

```bash
pip install -e ".[real-data]"
insightiq-data import-uci --source data/source/online_retail_II.xlsx
```

This creates `raw.public_online_retail` after filtering cancellations, non-positive quantity/price rows, and transactions without a customer ID. The workbook is not redistributed by this repository.
