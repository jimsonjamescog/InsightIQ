from __future__ import annotations

import hashlib
import os
import statistics
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from insightiq.models import ToolResult, new_id
from insightiq.tools.registry import ToolDefinition, ToolRegistry

MetricName = Literal["revenue", "orders", "traffic", "payment_failure_rate"]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KPIInput(ToolInput):
    metric: MetricName
    period: str = "latest"


class ComparePeriodsInput(ToolInput):
    metric: MetricName
    current_period: str = "latest"
    baseline_period: str = "previous_28_days"


class DecomposeKPIInput(ToolInput):
    metric: Literal["revenue"] = "revenue"
    current_period: str = "latest"
    baseline_period: str = "previous_28_days"


class SegmentMetricInput(ToolInput):
    metric: Literal["revenue", "orders"]
    dimension: Literal["region", "channel", "product_category"]
    period: str = "latest"


class DetectAnomalyInput(ToolInput):
    metric: MetricName
    window_days: int = Field(default=28, ge=7, le=90)


class DataQualityInput(ToolInput):
    field: Literal["customer_region", "customer_id", "order_total", "payment_status"]
    period: str = "latest"


class TimeWindowInput(ToolInput):
    start: str = "incident_window"
    end: str = "latest"


class SchemaChangeInput(ToolInput):
    object_name: str = "customer_dimension"
    period: str = "last_7_days"


class DependencyInput(ToolInput):
    object_name: str = "daily_revenue"


class IncidentSearchInput(ToolInput):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=50)


class BusinessImpactInput(ToolInput):
    metric: Literal["revenue"] = "revenue"


class QueryRunner(ABC):
    backend_name: str

    @abstractmethod
    def query(self, sql: str) -> list[dict[str, Any]]:
        raise NotImplementedError


class DuckDBRunner(QueryRunner):
    backend_name = "duckdb"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def query(self, sql: str) -> list[dict[str, Any]]:
        with duckdb.connect(str(self.path), read_only=True) as connection:
            cursor = connection.execute(sql)
            columns = [item[0].lower() for item in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


class SnowflakeRunner(QueryRunner):
    backend_name = "snowflake"

    def __init__(self) -> None:
        required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            raise RuntimeError(f"Missing Snowflake configuration: {', '.join(missing)}")

    def query(self, sql: str) -> list[dict[str, Any]]:
        try:
            import snowflake.connector
        except ImportError as error:
            raise RuntimeError(
                'Install Snowflake support with pip install -e ".[snowflake]"'
            ) from error
        connection = snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
            database=os.getenv("SNOWFLAKE_DATABASE", "INSIGHTIQ"),
            role=os.getenv("SNOWFLAKE_ROLE") or None,
        )
        try:
            cursor = connection.cursor(snowflake.connector.DictCursor)
            try:
                cursor.execute(sql)
                return [
                    {str(key).lower(): value for key, value in row.items()}
                    for row in cursor.fetchall()
                ]
            finally:
                cursor.close()
        finally:
            connection.close()


METRIC_SOURCES = {
    "revenue": ("business.daily_revenue", "revenue", "USD"),
    "orders": ("business.daily_revenue", "orders", "orders"),
    "traffic": ("business.daily_traffic", "traffic", "sessions"),
    "payment_failure_rate": (
        "business.daily_payment_metrics",
        "payment_failure_rate",
        "ratio",
    ),
}


class WarehouseToolProvider:
    def __init__(self, runner: QueryRunner) -> None:
        self.runner = runner

    def _result(self, tool: str, result: dict[str, Any], source: str, sql: str) -> ToolResult:
        digest = hashlib.sha256(sql.encode()).hexdigest()[:12]
        return ToolResult(
            tool_name=tool,
            execution_id=new_id("exec"),
            query_id=f"{self.runner.backend_name}:{digest}",
            source=source.upper(),
            result=result,
        )

    def _metric_history(self, metric: str) -> tuple[list[dict[str, Any]], str, str, str]:
        table, column, unit = METRIC_SOURCES[metric]
        sql = f"SELECT metric_date, {column} AS value FROM {table} ORDER BY metric_date DESC"
        return self.runner.query(sql), table, unit, sql

    def get_kpi(self, args: KPIInput) -> ToolResult:
        rows, source, unit, sql = self._metric_history(args.metric)
        current = rows[0]
        return self._result(
            "get_kpi",
            {
                "metric": args.metric,
                "period": str(current["metric_date"]),
                "value": float(current["value"]),
                "unit": unit,
            },
            source,
            sql,
        )

    def compare_periods(self, args: ComparePeriodsInput) -> ToolResult:
        rows, source, unit, sql = self._metric_history(args.metric)
        current = float(rows[0]["value"])
        baseline_values = [float(row["value"]) for row in rows[1:29]]
        baseline = statistics.mean(baseline_values)
        percent_change = ((current - baseline) / baseline) * 100 if baseline else 0.0
        return self._result(
            "compare_periods",
            {
                "metric": args.metric,
                "current_value": current,
                "baseline_value": baseline,
                "percent_change": round(percent_change, 2),
                "unit": unit,
                "current_period": str(rows[0]["metric_date"]),
                "baseline_period": args.baseline_period,
            },
            source,
            sql,
        )

    def decompose_kpi(self, args: DecomposeKPIInput) -> ToolResult:
        sql = (
            "SELECT metric_date, revenue, orders "
            "FROM business.daily_revenue ORDER BY metric_date DESC"
        )
        rows = self.runner.query(sql)
        current_revenue = float(rows[0]["revenue"])
        current_orders = float(rows[0]["orders"])
        baseline_revenue = statistics.mean(float(row["revenue"]) for row in rows[1:29])
        baseline_orders = statistics.mean(float(row["orders"]) for row in rows[1:29])
        current_aov = current_revenue / current_orders
        baseline_aov = baseline_revenue / baseline_orders
        volume_effect = (current_orders - baseline_orders) * baseline_aov
        aov_effect = current_orders * (current_aov - baseline_aov)
        return self._result(
            "decompose_kpi",
            {
                "metric": args.metric,
                "current": {
                    "revenue": current_revenue,
                    "orders": current_orders,
                    "aov": current_aov,
                },
                "baseline": {
                    "revenue": baseline_revenue,
                    "orders": baseline_orders,
                    "aov": baseline_aov,
                },
                "effects": {"order_volume": volume_effect, "average_order_value": aov_effect},
            },
            "business.daily_revenue",
            sql,
        )

    def segment_metric(self, args: SegmentMetricInput) -> ToolResult:
        dimension_column = {
            "region": "customer_region",
            "channel": "channel",
            "product_category": "product_category",
        }[args.dimension]
        sql = (
            "SELECT order_date AS metric_date, "
            f"{dimension_column} AS segment, order_total FROM business.fct_orders "
            "WHERE order_status = 'PAID' ORDER BY order_date DESC"
        )
        rows = self.runner.query(sql)
        current_date = rows[0]["metric_date"]
        prior_dates = sorted(
            {row["metric_date"] for row in rows if row["metric_date"] != current_date}, reverse=True
        )[:28]
        current: dict[str, float] = {}
        baseline_totals: dict[str, list[float]] = {}
        for row in rows:
            segment = row["segment"]
            if segment is None:
                continue
            value = float(row["order_total"]) if args.metric == "revenue" else 1.0
            if row["metric_date"] == current_date:
                current[segment] = current.get(segment, 0.0) + value
            elif row["metric_date"] in prior_dates:
                daily = baseline_totals.setdefault(segment, [0.0] * len(prior_dates))
                daily[prior_dates.index(row["metric_date"])] += value
        segments = []
        for segment in sorted(set(current) | set(baseline_totals)):
            current_value = current.get(segment, 0.0)
            baseline = statistics.mean(baseline_totals.get(segment, [0.0]))
            change = ((current_value - baseline) / baseline) * 100 if baseline else 0.0
            segments.append(
                {
                    "segment": segment,
                    "current": current_value,
                    "baseline": baseline,
                    "percent_change": round(change, 2),
                }
            )
        return self._result(
            "segment_metric",
            {"metric": args.metric, "dimension": args.dimension, "segments": segments},
            "business.fct_orders",
            sql,
        )

    def detect_anomaly(self, args: DetectAnomalyInput) -> ToolResult:
        rows, source, unit, sql = self._metric_history(args.metric)
        current = float(rows[0]["value"])
        history = [float(row["value"]) for row in rows[1 : args.window_days + 1]]
        mean = statistics.mean(history)
        deviation = statistics.pstdev(history)
        z_score = (
            (current - mean) / deviation if deviation else (0.0 if current == mean else -999.0)
        )
        return self._result(
            "detect_anomaly",
            {
                "metric": args.metric,
                "current_value": current,
                "baseline_mean": mean,
                "baseline_stddev": deviation,
                "z_score": round(z_score, 3),
                "is_anomaly": abs(z_score) >= 3,
                "unit": unit,
            },
            source,
            sql,
        )

    def check_data_quality(self, args: DataQualityInput) -> ToolResult:
        sql = (
            "SELECT metric_date, null_rate, row_count FROM quality.data_quality_metrics "
            f"WHERE field_name = '{args.field}' ORDER BY metric_date DESC"
        )
        rows = self.runner.query(sql)
        current = float(rows[0]["null_rate"])
        baseline = statistics.mean(float(row["null_rate"]) for row in rows[1:29])
        return self._result(
            "check_data_quality",
            {
                "field": args.field,
                "current_null_rate": current,
                "baseline_null_rate": baseline,
                "anomaly": current > max(0.05, baseline * 5),
                "row_count": rows[0]["row_count"],
            },
            "quality.data_quality_metrics",
            sql,
        )

    def get_deployments(self, args: TimeWindowInput) -> ToolResult:
        sql = "SELECT * FROM operations.deployments ORDER BY deployed_at DESC"
        rows = self.runner.query(sql)
        return self._result("get_deployments", {"deployments": rows}, "operations.deployments", sql)

    def get_pipeline_runs(self, args: TimeWindowInput) -> ToolResult:
        sql = "SELECT * FROM operations.pipeline_runs ORDER BY started_at DESC"
        rows = self.runner.query(sql)
        return self._result("get_pipeline_runs", {"runs": rows}, "operations.pipeline_runs", sql)

    def inspect_schema_changes(self, args: SchemaChangeInput) -> ToolResult:
        sql = "SELECT * FROM operations.schema_changes ORDER BY changed_at DESC"
        rows = [row for row in self.runner.query(sql) if row["object_name"] == args.object_name]
        return self._result(
            "inspect_schema_changes",
            {"object_name": args.object_name, "changes": rows},
            "operations.schema_changes",
            sql,
        )

    def get_dependencies(self, args: DependencyInput) -> ToolResult:
        sql = "SELECT * FROM operations.data_dependencies ORDER BY dependency_order"
        all_rows = self.runner.query(sql)
        frontier = {args.object_name}
        rows = []
        for row in all_rows:
            if row["downstream_object"] in frontier:
                rows.append(row)
                frontier.add(row["upstream_object"])
        return self._result(
            "get_dependencies",
            {
                "object_name": args.object_name,
                "upstream": [row["upstream_object"] for row in rows],
                "filter_logic": next(
                    (row["filter_logic"] for row in rows if row["filter_logic"]), None
                ),
                "affected_path": [args.object_name, *[row["upstream_object"] for row in rows]],
                "dependencies": rows,
            },
            "operations.data_dependencies",
            sql,
        )

    def search_incidents(self, args: IncidentSearchInput) -> ToolResult:
        sql = "SELECT * FROM operations.incidents ORDER BY created_at DESC"
        query = args.query.casefold()
        rows = [
            row
            for row in self.runner.query(sql)
            if query in f"{row['title']} {row['category']} {row['content']}".casefold()
        ][: args.limit]
        return self._result(
            "search_incidents",
            {"query": args.query, "incidents": rows},
            "operations.incidents",
            sql,
        )

    def calculate_business_impact(self, args: BusinessImpactInput) -> ToolResult:
        sql = "SELECT metric_date, revenue FROM business.daily_revenue ORDER BY metric_date DESC"
        rows = self.runner.query(sql)
        current_value = float(rows[0]["revenue"])
        expected_value = statistics.mean(float(row["revenue"]) for row in rows[1:29])
        difference = expected_value - current_value
        percent = (difference / expected_value) * 100 if expected_value else 0.0
        return self._result(
            "calculate_business_impact",
            {
                "metric": args.metric,
                "reported_value": current_value,
                "expected_value": expected_value,
                "understatement": difference,
                "understatement_percent": round(percent, 2),
                "unit": "USD",
            },
            "business.daily_revenue",
            sql,
        )


def build_warehouse_registry(runner: QueryRunner) -> ToolRegistry:
    provider = WarehouseToolProvider(runner)
    definitions = [
        ("get_kpi", "Read the latest value of an allowlisted KPI.", KPIInput, provider.get_kpi),
        (
            "compare_periods",
            "Compare an allowlisted KPI with its prior 28-day baseline.",
            ComparePeriodsInput,
            provider.compare_periods,
        ),
        (
            "decompose_kpi",
            "Decompose revenue change into order-volume and AOV effects.",
            DecomposeKPIInput,
            provider.decompose_kpi,
        ),
        (
            "segment_metric",
            "Break revenue or orders down by an allowlisted dimension.",
            SegmentMetricInput,
            provider.segment_metric,
        ),
        (
            "detect_anomaly",
            "Measure an allowlisted KPI against its historical distribution.",
            DetectAnomalyInput,
            provider.detect_anomaly,
        ),
        (
            "check_data_quality",
            "Compare field null rate with its historical baseline.",
            DataQualityInput,
            provider.check_data_quality,
        ),
        ("get_deployments", "List deployment records.", TimeWindowInput, provider.get_deployments),
        (
            "get_pipeline_runs",
            "List data-pipeline run outcomes.",
            TimeWindowInput,
            provider.get_pipeline_runs,
        ),
        (
            "inspect_schema_changes",
            "Inspect recorded changes to an allowlisted object.",
            SchemaChangeInput,
            provider.inspect_schema_changes,
        ),
        (
            "get_dependencies",
            "Trace upstream data dependencies and filters.",
            DependencyInput,
            provider.get_dependencies,
        ),
        (
            "search_incidents",
            "Search historical incident metadata.",
            IncidentSearchInput,
            provider.search_incidents,
        ),
        (
            "calculate_business_impact",
            "Calculate deterministic financial impact.",
            BusinessImpactInput,
            provider.calculate_business_impact,
        ),
    ]
    registry = ToolRegistry()
    for name, description, input_model, handler in definitions:
        registry.register(
            ToolDefinition(
                name=name,
                description=description,
                input_model=input_model,
                handler=handler,
            )
        )
    return registry
