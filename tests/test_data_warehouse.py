from pathlib import Path

from insightiq.data.warehouse import build_warehouse, validate_warehouse
from insightiq.tools.warehouse import DuckDBRunner, build_warehouse_registry


def test_builds_and_validates_reproducible_warehouse(tmp_path: Path):
    path = tmp_path / "insightiq.duckdb"
    profile = build_warehouse(path)

    assert profile.history_days == 90
    assert profile.customers == 1000
    assert profile.orders == 9000
    assert profile.incident_actual_revenue == 120000
    assert profile.incident_reported_revenue == 72000
    assert round(profile.incident_region_null_rate, 3) == 0.631
    assert validate_warehouse(path) == []


def test_all_de3_warehouse_tools_execute(tmp_path: Path):
    path = tmp_path / "insightiq.duckdb"
    build_warehouse(path)
    registry = build_warehouse_registry(DuckDBRunner(path))

    inputs = {
        "get_kpi": {"metric": "revenue"},
        "compare_periods": {"metric": "revenue"},
        "decompose_kpi": {},
        "segment_metric": {"metric": "revenue", "dimension": "region"},
        "detect_anomaly": {"metric": "revenue"},
        "check_data_quality": {"field": "customer_region"},
        "get_deployments": {},
        "get_pipeline_runs": {},
        "inspect_schema_changes": {},
        "get_dependencies": {},
        "search_incidents": {"query": "payment"},
        "calculate_business_impact": {
            "metric": "revenue",
            "current_value": 72000,
            "expected_value": 120000,
        },
    }

    assert set(inputs) == set(registry.names)
    results = {name: registry.execute(name, arguments) for name, arguments in inputs.items()}
    assert all(result.query_id.startswith("duckdb:") for result in results.values())
    assert results["compare_periods"].result["percent_change"] == -40.0
    assert results["check_data_quality"].result["current_null_rate"] == 0.631
    assert results["get_deployments"].result["deployments"][0]["deployment_id"] == "deploy-284"
    assert results["calculate_business_impact"].result["understatement"] == 48000


def test_warehouse_investigation_path(tmp_path: Path):
    from insightiq.agent.investigator import Investigator
    from insightiq.agent.providers import DeterministicDecisionProvider

    path = tmp_path / "insightiq.duckdb"
    build_warehouse(path)
    registry = build_warehouse_registry(DuckDBRunner(path))
    _, report = Investigator(registry, DeterministicDecisionProvider()).investigate(
        "Why did reported revenue decrease yesterday?"
    )

    assert report.evidence_gate.passed
    assert report.confidence.overall > 0.9
    assert report.business_impact["understatement"] == 48000
