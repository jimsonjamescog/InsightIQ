from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

import duckdb

HISTORY_START = "2026-06-17"
INCIDENT_DATE = "2026-09-14"


class ScenarioName(StrEnum):
    BASE = "base"
    CUSTOM_REGION_FAILURE = "custom_region_failure"
    MISSING_DEPLOYMENT = "missing_deployment"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    PAYMENT_FAILURE = "payment_failure"
    DATA_QUALITY_NO_DEPLOYMENT = "data_quality_no_deployment"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class WarehouseProfile:
    history_days: int
    customers: int
    orders: int
    products: int
    incident_actual_revenue: float
    incident_reported_revenue: float
    incident_region_null_rate: float

    def to_dict(self) -> dict:
        return asdict(self)


DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS business;
CREATE SCHEMA IF NOT EXISTS quality;
CREATE SCHEMA IF NOT EXISTS operations;

CREATE OR REPLACE TABLE raw.customers AS
SELECT
    customer_number AS customer_id,
    'Customer ' || customer_number AS customer_name,
    CASE
        WHEN customer_number <= 369 THEN 'NA'
        WHEN customer_number <= 700 THEN 'EU'
        ELSE 'APAC'
    END AS region_code,
    CASE customer_number % 3
        WHEN 0 THEN 'direct' WHEN 1 THEN 'organic' ELSE 'partner'
    END AS channel,
    DATE '2025-01-01' + CAST(customer_number % 365 AS INTEGER) AS created_at
FROM range(1, 1001) AS t(customer_number);

CREATE OR REPLACE TABLE raw.products AS
SELECT
    product_number AS product_id,
    'Product ' || product_number AS product_name,
    CASE product_number % 3
        WHEN 0 THEN 'Software' WHEN 1 THEN 'Services' ELSE 'Hardware'
    END AS category,
    1200.00::DECIMAL(12, 2) AS unit_price
FROM range(1, 61) AS t(product_number);

CREATE OR REPLACE TABLE raw.orders AS
WITH days AS (
    SELECT CAST(day AS DATE) AS order_date
    FROM generate_series(DATE '2026-06-17', DATE '2026-09-14', INTERVAL 1 DAY) AS t(day)
), numbered AS (
    SELECT order_date, order_number
    FROM days CROSS JOIN range(0, 100) AS t(order_number)
)
SELECT
    row_number() OVER (ORDER BY order_date, order_number) AS order_id,
    CASE
        WHEN order_number < 60 THEN 1 + CAST((order_number * 6) % 369 AS INTEGER)
        WHEN order_number < 82 THEN 370 + CAST(((order_number - 60) * 15) % 331 AS INTEGER)
        ELSE 701 + CAST(((order_number - 82) * 16) % 300 AS INTEGER)
    END AS customer_id,
    order_date,
    TIMESTAMP '2026-06-17 12:00:00'
        + CAST(order_date - DATE '2026-06-17' AS INTEGER) * INTERVAL 1 DAY AS ordered_at,
    CASE order_number % 3 WHEN 0 THEN 'direct' WHEN 1 THEN 'organic' ELSE 'partner' END AS channel,
    'PAID' AS order_status,
    1200.00::DECIMAL(12, 2) AS order_total
FROM numbered;

CREATE OR REPLACE TABLE raw.order_items AS
SELECT
    order_id AS order_item_id,
    order_id,
    1 + CAST(order_id % 60 AS INTEGER) AS product_id,
    1 AS quantity,
    1200.00::DECIMAL(12, 2) AS unit_price,
    1200.00::DECIMAL(12, 2) AS line_total
FROM raw.orders;

CREATE OR REPLACE TABLE raw.web_traffic AS
SELECT
    CAST(day AS DATE) AS traffic_date,
    CASE WHEN CAST(day AS DATE) = DATE '2026-09-14' THEN 100800 ELSE 100000 END AS sessions,
    5000 AS checkout_sessions
FROM generate_series(DATE '2026-06-17', DATE '2026-09-14', INTERVAL 1 DAY) AS t(day);

CREATE OR REPLACE TABLE raw.payments AS
WITH successful AS (
    SELECT
        'pay-' || order_id AS payment_attempt_id,
        order_id,
        order_date AS payment_date,
        'SUCCEEDED' AS status,
        order_total AS amount
    FROM raw.orders
), failed AS (
    SELECT
        'fail-' || CAST(order_date AS VARCHAR) || '-' || attempt_number AS payment_attempt_id,
        NULL::BIGINT AS order_id,
        order_date AS payment_date,
        'FAILED' AS status,
        1200.00::DECIMAL(12, 2) AS amount
    FROM (SELECT DISTINCT order_date FROM raw.orders)
    CROSS JOIN range(1, 3) AS t(attempt_number)
)
SELECT * FROM successful UNION ALL SELECT * FROM failed;

CREATE OR REPLACE TABLE business.customer_dimension_snapshot AS
SELECT
    snapshot_date,
    customer_id,
    customer_name,
    region_code,
    CASE
        WHEN snapshot_date = DATE '2026-09-14' AND region_code <> 'NA' THEN NULL
        WHEN snapshot_date < DATE '2026-09-14' AND customer_id > 996 THEN NULL
        WHEN region_code = 'NA' THEN 'North America'
        WHEN region_code = 'EU' THEN 'Europe'
        WHEN region_code = 'APAC' THEN 'Asia Pacific'
    END AS customer_region,
    channel
FROM raw.customers
CROSS JOIN (
    SELECT CAST(day AS DATE) AS snapshot_date
    FROM generate_series(DATE '2026-06-17', DATE '2026-09-14', INTERVAL 1 DAY) AS t(day)
);

CREATE OR REPLACE TABLE business.fct_orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.ordered_at,
    o.channel,
    o.order_status,
    o.order_total,
    d.customer_region,
    p.category AS product_category
FROM raw.orders o
JOIN business.customer_dimension_snapshot d
  ON d.customer_id = o.customer_id AND d.snapshot_date = o.order_date
JOIN raw.order_items i ON i.order_id = o.order_id
JOIN raw.products p ON p.product_id = i.product_id;

CREATE OR REPLACE TABLE business.daily_actual_revenue AS
SELECT order_date AS metric_date, SUM(order_total)::DOUBLE AS revenue, COUNT(*) AS orders
FROM business.fct_orders
WHERE order_status = 'PAID'
GROUP BY order_date;

CREATE OR REPLACE TABLE business.daily_revenue AS
SELECT order_date AS metric_date, SUM(order_total)::DOUBLE AS revenue, COUNT(*) AS orders
FROM business.fct_orders
WHERE order_status = 'PAID' AND customer_region IS NOT NULL
GROUP BY order_date;

CREATE OR REPLACE TABLE business.regional_revenue AS
SELECT order_date AS metric_date, customer_region AS region,
       SUM(order_total)::DOUBLE AS revenue, COUNT(*) AS orders
FROM business.fct_orders
WHERE order_status = 'PAID' AND customer_region IS NOT NULL
GROUP BY order_date, customer_region;

CREATE OR REPLACE TABLE business.daily_traffic AS
SELECT traffic_date AS metric_date, sessions::DOUBLE AS traffic
FROM raw.web_traffic;

CREATE OR REPLACE TABLE business.daily_payment_metrics AS
SELECT payment_date AS metric_date,
       SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END)::DOUBLE
           / COUNT(*) AS payment_failure_rate,
       COUNT(*) AS payment_attempts
FROM raw.payments
GROUP BY payment_date;

CREATE OR REPLACE TABLE quality.data_quality_metrics AS
SELECT
    snapshot_date AS metric_date,
    'customer_region' AS field_name,
    SUM(CASE WHEN customer_region IS NULL THEN 1 ELSE 0 END)::DOUBLE / COUNT(*) AS null_rate,
    COUNT(*) AS row_count
FROM business.customer_dimension_snapshot
GROUP BY snapshot_date
UNION ALL
SELECT DISTINCT order_date, 'customer_id', 0.0, 1000 FROM raw.orders
UNION ALL
SELECT DISTINCT order_date, 'order_total', 0.001, 1000 FROM raw.orders
UNION ALL
SELECT DISTINCT payment_date, 'payment_status', 0.0, 1000 FROM raw.payments;
"""


OPERATIONS_DDL = """
CREATE OR REPLACE TABLE operations.deployments (
    deployment_id VARCHAR, service VARCHAR, deployed_at TIMESTAMP,
    summary VARCHAR, status VARCHAR
);
INSERT INTO operations.deployments VALUES
    ('deploy-284', 'customer-transform', TIMESTAMP '2026-09-14 02:10:00',
     'Standardize customer region codes', 'succeeded'),
    ('deploy-283', 'checkout-ui', TIMESTAMP '2026-09-13 18:00:00',
     'Update checkout button styling', 'succeeded'),
    ('deploy-282', 'recommendation-api', TIMESTAMP '2026-09-13 10:00:00',
     'Tune product ranking weights', 'succeeded');

CREATE OR REPLACE TABLE operations.pipeline_runs (
    run_id VARCHAR, pipeline VARCHAR, started_at TIMESTAMP, completed_at TIMESTAMP,
    status VARCHAR, rows_written BIGINT, error_message VARCHAR
);
INSERT INTO operations.pipeline_runs VALUES
    ('run-901', 'daily_revenue', TIMESTAMP '2026-09-14 03:00:00',
     TIMESTAMP '2026-09-14 03:05:00', 'succeeded', 60, NULL),
    ('run-900', 'customer_dimension', TIMESTAMP '2026-09-14 02:30:00',
     TIMESTAMP '2026-09-14 02:34:00', 'succeeded', 1000, NULL),
    ('run-899', 'payment_metrics', TIMESTAMP '2026-09-14 02:20:00',
     TIMESTAMP '2026-09-14 02:22:00', 'succeeded', 102, NULL);

CREATE OR REPLACE TABLE operations.schema_changes (
    change_id VARCHAR, deployment_id VARCHAR, object_name VARCHAR, column_name VARCHAR,
    change_description VARCHAR, changed_at TIMESTAMP
);
INSERT INTO operations.schema_changes VALUES
    ('change-71', 'deploy-284', 'customer_dimension', 'customer_region',
     'Mapping now expects ISO-3166 region codes; legacy values map to NULL',
     TIMESTAMP '2026-09-14 02:10:00'),
    ('change-70', 'deploy-283', 'checkout_events', 'button_variant',
     'Added optional visual experiment attribute', TIMESTAMP '2026-09-13 18:00:00');

CREATE OR REPLACE TABLE operations.data_dependencies (
    downstream_object VARCHAR, upstream_object VARCHAR, dependency_order INTEGER,
    relationship VARCHAR, filter_logic VARCHAR
);
INSERT INTO operations.data_dependencies VALUES
    ('daily_revenue', 'regional_revenue', 1, 'aggregates', NULL),
    ('regional_revenue', 'fct_orders', 2, 'aggregates', 'customer_region IS NOT NULL'),
    ('fct_orders', 'customer_dimension', 3, 'joins', 'customer_id and snapshot_date'),
    ('customer_dimension', 'raw.customers', 4, 'transforms', 'region code mapping');

CREATE OR REPLACE TABLE operations.incidents (
    incident_id VARCHAR, title VARCHAR, category VARCHAR, content VARCHAR,
    created_at TIMESTAMP, resolved_at TIMESTAMP
);
INSERT INTO operations.incidents VALUES
    ('incident-41', 'Payment provider latency', 'payments',
     'Elevated latency without a material change in payment failures.',
     TIMESTAMP '2026-09-10 13:00:00', TIMESTAMP '2026-09-10 13:30:00'),
    ('incident-40', 'Campaign traffic spike', 'marketing',
     'Organic sessions increased after a campaign launch.',
     TIMESTAMP '2026-09-08 10:00:00', TIMESTAMP '2026-09-08 11:00:00');

CREATE OR REPLACE TABLE operations.documents (
    document_id VARCHAR, title VARCHAR, category VARCHAR, content VARCHAR, created_at TIMESTAMP
);
INSERT INTO operations.documents VALUES
    ('doc-1', 'Revenue model contract', 'data-contract',
     'Reported revenue requires a non-null customer_region and paid order status.',
     TIMESTAMP '2026-06-01 00:00:00');
"""


REBUILD_FACT_ORDERS = """
CREATE OR REPLACE TABLE business.fct_orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.ordered_at,
    o.channel,
    o.order_status,
    o.order_total,
    d.customer_region,
    p.category AS product_category
FROM raw.orders o
JOIN business.customer_dimension_snapshot d
  ON d.customer_id = o.customer_id AND d.snapshot_date = o.order_date
JOIN raw.order_items i ON i.order_id = o.order_id
JOIN raw.products p ON p.product_id = i.product_id;
"""

REBUILD_ANALYTICS = """
CREATE OR REPLACE TABLE business.daily_actual_revenue AS
SELECT order_date AS metric_date, SUM(order_total)::DOUBLE AS revenue, COUNT(*) AS orders
FROM business.fct_orders
WHERE order_status = 'PAID'
GROUP BY order_date;

CREATE OR REPLACE TABLE business.daily_revenue AS
SELECT order_date AS metric_date, SUM(order_total)::DOUBLE AS revenue, COUNT(*) AS orders
FROM business.fct_orders
WHERE order_status = 'PAID' AND customer_region IS NOT NULL
GROUP BY order_date;

CREATE OR REPLACE TABLE business.regional_revenue AS
SELECT order_date AS metric_date, customer_region AS region,
       SUM(order_total)::DOUBLE AS revenue, COUNT(*) AS orders
FROM business.fct_orders
WHERE order_status = 'PAID' AND customer_region IS NOT NULL
GROUP BY order_date, customer_region;

CREATE OR REPLACE TABLE business.daily_payment_metrics AS
SELECT payment_date AS metric_date,
       SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END)::DOUBLE
           / COUNT(*) AS payment_failure_rate,
       COUNT(*) AS payment_attempts
FROM raw.payments
GROUP BY payment_date;

CREATE OR REPLACE TABLE quality.data_quality_metrics AS
SELECT snapshot_date AS metric_date, 'customer_region' AS field_name,
       SUM(CASE WHEN customer_region IS NULL THEN 1 ELSE 0 END)::DOUBLE / COUNT(*) AS null_rate,
       COUNT(*) AS row_count
FROM business.customer_dimension_snapshot
GROUP BY snapshot_date
UNION ALL
SELECT DISTINCT order_date, 'customer_id', 0.0, 1000 FROM raw.orders
UNION ALL
SELECT DISTINCT order_date, 'order_total', 0.001, 1000 FROM raw.orders
UNION ALL
SELECT DISTINCT payment_date, 'payment_status', 0.0, 1000 FROM raw.payments;
"""


def _apply_scenario(connection, scenario: ScenarioName) -> None:
    if scenario == ScenarioName.BASE:
        return
    if scenario == ScenarioName.CUSTOM_REGION_FAILURE:
        connection.execute(
            """
            UPDATE business.customer_dimension_snapshot
            SET customer_region = NULL
            WHERE snapshot_date = DATE '2026-09-14'
            """
        )
        connection.execute(REBUILD_FACT_ORDERS)
        connection.execute(REBUILD_ANALYTICS)
        return
    if scenario == ScenarioName.MISSING_DEPLOYMENT:
        connection.execute("DELETE FROM operations.deployments WHERE deployment_id = 'deploy-284'")
        return
    if scenario == ScenarioName.CONFLICTING_EVIDENCE:
        connection.execute(
            """
            UPDATE quality.data_quality_metrics SET null_rate = 0.004
            WHERE metric_date = DATE '2026-09-14' AND field_name = 'customer_region'
            """
        )
        return
    if scenario == ScenarioName.DATA_QUALITY_NO_DEPLOYMENT:
        connection.execute("DELETE FROM operations.deployments WHERE deployment_id = 'deploy-284'")
        connection.execute(
            "DELETE FROM operations.schema_changes WHERE deployment_id = 'deploy-284'"
        )
        return
    if scenario == ScenarioName.INSUFFICIENT_EVIDENCE:
        connection.execute("DELETE FROM operations.deployments WHERE deployment_id = 'deploy-284'")
        connection.execute(
            "DELETE FROM operations.schema_changes WHERE deployment_id = 'deploy-284'"
        )
        connection.execute("DELETE FROM operations.data_dependencies")
        connection.execute(
            """
            UPDATE quality.data_quality_metrics SET null_rate = 0.004
            WHERE metric_date = DATE '2026-09-14' AND field_name = 'customer_region'
            """
        )
        return
    if scenario == ScenarioName.PAYMENT_FAILURE:
        connection.execute(
            """
            UPDATE business.customer_dimension_snapshot
            SET customer_region = CASE region_code
                WHEN 'NA' THEN 'North America'
                WHEN 'EU' THEN 'Europe'
                WHEN 'APAC' THEN 'Asia Pacific'
            END
            WHERE snapshot_date = DATE '2026-09-14'
            """
        )
        connection.execute(
            """
            UPDATE raw.orders SET order_status = 'PAYMENT_FAILED'
            WHERE order_id IN (
                SELECT order_id FROM raw.orders
                WHERE order_date = DATE '2026-09-14'
                ORDER BY order_id DESC LIMIT 40
            )
            """
        )
        connection.execute(
            """
            UPDATE raw.payments SET status = 'FAILED'
            WHERE order_id IN (
                SELECT order_id FROM raw.orders WHERE order_status = 'PAYMENT_FAILED'
            )
            """
        )
        connection.execute(
            """
            UPDATE business.fct_orders AS fact
            SET order_status = source.order_status,
                customer_region = snapshot.customer_region
            FROM raw.orders AS source, business.customer_dimension_snapshot AS snapshot
            WHERE fact.order_id = source.order_id
              AND snapshot.customer_id = fact.customer_id
              AND snapshot.snapshot_date = fact.order_date
            """
        )
        connection.execute("DELETE FROM operations.deployments WHERE deployment_id = 'deploy-284'")
        connection.execute(
            "DELETE FROM operations.schema_changes WHERE deployment_id = 'deploy-284'"
        )
        connection.execute(REBUILD_ANALYTICS)


def build_warehouse(
    path: str | Path,
    *,
    reset: bool = False,
    scenario: ScenarioName | str = ScenarioName.BASE,
) -> WarehouseProfile:
    scenario = ScenarioName(scenario)
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if reset and database_path.exists():
        database_path.unlink()
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(DDL)
        connection.execute(OPERATIONS_DDL)
        _apply_scenario(connection, scenario)
    errors = validate_warehouse(database_path, scenario=scenario)
    if errors:
        raise RuntimeError("Warehouse validation failed: " + "; ".join(errors))
    return profile_warehouse(database_path)


def profile_warehouse(path: str | Path) -> WarehouseProfile:
    with duckdb.connect(str(path), read_only=True) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(DISTINCT order_date) FROM raw.orders),
                (SELECT COUNT(*) FROM raw.customers),
                (SELECT COUNT(*) FROM raw.orders),
                (SELECT COUNT(*) FROM raw.products),
                COALESCE((SELECT revenue FROM business.daily_actual_revenue
                          WHERE metric_date = DATE '2026-09-14'), 0.0),
                COALESCE((SELECT revenue FROM business.daily_revenue
                          WHERE metric_date = DATE '2026-09-14'), 0.0),
                COALESCE((SELECT null_rate FROM quality.data_quality_metrics
                          WHERE metric_date = DATE '2026-09-14'
                            AND field_name = 'customer_region'), 0.0)
            """
        ).fetchone()
    return WarehouseProfile(*row)


def validate_warehouse(
    path: str | Path, scenario: ScenarioName | str = ScenarioName.BASE
) -> list[str]:
    scenario = ScenarioName(scenario)
    errors: list[str] = []
    profile = profile_warehouse(path)
    if profile.history_days != 90:
        errors.append(f"Expected 90 history days; got {profile.history_days}.")
    if profile.customers != 1000:
        errors.append(f"Expected 1000 customers; got {profile.customers}.")
    expected_actual = 72000 if scenario == ScenarioName.PAYMENT_FAILURE else 120000
    if profile.incident_actual_revenue != expected_actual:
        errors.append(f"Incident actual revenue must be {expected_actual}.")
    expected_reported_revenue = (
        0.0
        if scenario == ScenarioName.CUSTOM_REGION_FAILURE
        else 72000
    )
    if profile.incident_reported_revenue != expected_reported_revenue:
        errors.append(f"Incident reported revenue must be {expected_reported_revenue}.")
    expected_null_rate = (
        0.0
        if scenario == ScenarioName.PAYMENT_FAILURE
        else 0.004
        if scenario in {ScenarioName.CONFLICTING_EVIDENCE, ScenarioName.INSUFFICIENT_EVIDENCE}
        else 1.0
        if scenario == ScenarioName.CUSTOM_REGION_FAILURE
        else 0.631
    )
    if round(profile.incident_region_null_rate, 3) != expected_null_rate:
        errors.append(f"Incident customer-region null rate must be {expected_null_rate:.3f}.")
    return errors
