from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from insightiq.models import ToolResult, new_id
from insightiq.tools.registry import ToolDefinition, ToolRegistry


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComparePeriodsInput(ToolInput):
    metric: Literal["revenue", "orders", "traffic", "payment_failure_rate"]
    current_period: str = "yesterday"
    baseline_period: str = "previous_28_days"


class SegmentMetricInput(ToolInput):
    metric: Literal["revenue", "orders"]
    dimension: Literal["region", "channel", "product_category"]
    period: str = "yesterday"


class DataQualityInput(ToolInput):
    field: Literal["customer_region", "customer_id", "order_total", "payment_status"]
    period: str = "last_7_days"


class TimeWindowInput(ToolInput):
    start: str = "yesterday"
    end: str = "today"


class SchemaChangeInput(ToolInput):
    object_name: str = "customer_dimension"
    period: str = "last_7_days"


class DependencyInput(ToolInput):
    object_name: str = "daily_revenue"


class BusinessImpactInput(ToolInput):
    metric: Literal["revenue"] = "revenue"


SCENARIO: dict[str, Any] = {
    "periods": {
        "revenue": {"current": 72000.0, "baseline": 120000.0, "unit": "USD"},
        "orders": {"current": 1188.0, "baseline": 1980.0, "unit": "orders"},
        "traffic": {"current": 100800.0, "baseline": 100000.0, "unit": "sessions"},
        "payment_failure_rate": {"current": 0.021, "baseline": 0.020, "unit": "ratio"},
    },
    "segments": {
        "region": {
            "North America": {"current": 54000, "baseline": 55000},
            "Europe": {"current": 9800, "baseline": 36000},
            "Asia Pacific": {"current": 8200, "baseline": 29000},
        }
    },
    "quality": {
        "customer_region": {"current_null_rate": 0.631, "baseline_null_rate": 0.004},
        "customer_id": {"current_null_rate": 0.0, "baseline_null_rate": 0.0},
        "order_total": {"current_null_rate": 0.001, "baseline_null_rate": 0.001},
        "payment_status": {"current_null_rate": 0.0, "baseline_null_rate": 0.0},
    },
}


def _result(tool: str, result: dict[str, Any], source: str, query: str) -> ToolResult:
    return ToolResult(
        tool_name=tool,
        execution_id=new_id("exec"),
        query_id=f"mock:{query}",
        source=source,
        result=result,
    )


def compare_periods(args: ComparePeriodsInput) -> ToolResult:
    values = SCENARIO["periods"][args.metric]
    baseline = values["baseline"]
    percent_change = ((values["current"] - baseline) / baseline) * 100 if baseline else 0
    return _result(
        "compare_periods",
        {
            "metric": args.metric,
            "current_value": values["current"],
            "baseline_value": baseline,
            "percent_change": round(percent_change, 2),
            "unit": values["unit"],
            "current_period": args.current_period,
            "baseline_period": args.baseline_period,
        },
        "INSIGHTIQ.BUSINESS.DAILY_KPIS",
        f"compare-{args.metric}",
    )


def segment_metric(args: SegmentMetricInput) -> ToolResult:
    if args.dimension == "region":
        segments = SCENARIO["segments"]["region"]
    else:
        segments = {
            "primary": {"current": 60000, "baseline": 100000},
            "other": {"current": 12000, "baseline": 20000},
        }
    output = []
    for name, values in segments.items():
        change = ((values["current"] - values["baseline"]) / values["baseline"]) * 100
        output.append({"segment": name, **values, "percent_change": round(change, 2)})
    return _result(
        "segment_metric",
        {"metric": args.metric, "dimension": args.dimension, "segments": output},
        "INSIGHTIQ.BUSINESS.REGIONAL_REVENUE",
        f"segment-{args.metric}-{args.dimension}",
    )


def check_data_quality(args: DataQualityInput) -> ToolResult:
    quality = SCENARIO["quality"][args.field]
    return _result(
        "check_data_quality",
        {"field": args.field, **quality, "anomaly": quality["current_null_rate"] > 0.05},
        "INSIGHTIQ.QUALITY.DATA_QUALITY_METRICS",
        f"quality-{args.field}",
    )


def get_deployments(args: TimeWindowInput) -> ToolResult:
    return _result(
        "get_deployments",
        {
            "deployments": [
                {
                    "deployment_id": "deploy-284",
                    "service": "customer-transform",
                    "deployed_at": "2026-09-14T02:10:00Z",
                    "summary": "Standardize customer region codes",
                    "status": "succeeded",
                },
                {
                    "deployment_id": "deploy-283",
                    "service": "checkout-ui",
                    "deployed_at": "2026-09-13T18:00:00Z",
                    "summary": "Update button styling",
                    "status": "succeeded",
                },
            ]
        },
        "INSIGHTIQ.OPERATIONS.DEPLOYMENTS",
        "deployments-window",
    )


def get_pipeline_runs(args: TimeWindowInput) -> ToolResult:
    return _result(
        "get_pipeline_runs",
        {
            "runs": [
                {
                    "pipeline": "daily_revenue",
                    "status": "succeeded",
                    "rows_written": 1188,
                    "completed_at": "2026-09-14T03:05:00Z",
                }
            ]
        },
        "INSIGHTIQ.OPERATIONS.PIPELINE_RUNS",
        "pipeline-runs-window",
    )


def inspect_schema_changes(args: SchemaChangeInput) -> ToolResult:
    return _result(
        "inspect_schema_changes",
        {
            "object_name": args.object_name,
            "changes": [
                {
                    "deployment_id": "deploy-284",
                    "column": "customer_region",
                    "change": (
                        "Mapping now expects ISO-3166 region codes; legacy values map to NULL"
                    ),
                    "changed_at": "2026-09-14T02:10:00Z",
                }
            ],
        },
        "INSIGHTIQ.OPERATIONS.SCHEMA_CHANGES",
        f"schema-{args.object_name}",
    )


def get_dependencies(args: DependencyInput) -> ToolResult:
    return _result(
        "get_dependencies",
        {
            "object_name": args.object_name,
            "upstream": ["orders", "customers", "customer_dimension"],
            "filter_logic": "WHERE customer_region IS NOT NULL",
            "affected_path": [
                "customer_dimension.customer_region",
                "regional_revenue",
                "daily_revenue",
            ],
        },
        "INSIGHTIQ.OPERATIONS.DATA_DEPENDENCIES",
        f"dependencies-{args.object_name}",
    )


def calculate_business_impact(args: BusinessImpactInput) -> ToolResult:
    current_value = SCENARIO["periods"][args.metric]["current"]
    expected_value = SCENARIO["periods"][args.metric]["baseline"]
    difference = expected_value - current_value
    percent = (difference / expected_value) * 100 if expected_value else 0
    return _result(
        "calculate_business_impact",
        {
            "metric": args.metric,
            "reported_value": current_value,
            "expected_value": expected_value,
            "understatement": difference,
            "understatement_percent": round(percent, 2),
            "unit": "USD",
        },
        "INSIGHTIQ.BUSINESS.DAILY_REVENUE",
        "impact-revenue",
    )


def build_mock_registry() -> ToolRegistry:
    registry = ToolRegistry()
    definitions = [
        (
            "compare_periods",
            "Compare a KPI with its historical baseline.",
            ComparePeriodsInput,
            compare_periods,
        ),
        (
            "segment_metric",
            "Break a KPI down by an allowlisted dimension.",
            SegmentMetricInput,
            segment_metric,
        ),
        (
            "check_data_quality",
            "Compare field quality with its baseline.",
            DataQualityInput,
            check_data_quality,
        ),
        ("get_deployments", "List deployments in a time window.", TimeWindowInput, get_deployments),
        (
            "get_pipeline_runs",
            "List data pipeline outcomes in a time window.",
            TimeWindowInput,
            get_pipeline_runs,
        ),
        (
            "inspect_schema_changes",
            "Inspect recorded changes to a data object.",
            SchemaChangeInput,
            inspect_schema_changes,
        ),
        (
            "get_dependencies",
            "Get allowlisted upstream dependencies and filter logic.",
            DependencyInput,
            get_dependencies,
        ),
        (
            "calculate_business_impact",
            "Calculate deterministic financial impact.",
            BusinessImpactInput,
            calculate_business_impact,
        ),
    ]
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
