import pytest
from pydantic import ValidationError

from insightiq.tools import build_mock_registry


def test_revenue_comparison_is_deterministic():
    result = build_mock_registry().execute("compare_periods", {"metric": "revenue"})
    assert result.result["percent_change"] == -40.0
    assert result.query_id
    assert result.source


def test_tool_registry_rejects_unknown_tool():
    with pytest.raises(ValueError, match="not allowlisted"):
        build_mock_registry().execute("run_arbitrary_sql", {})


def test_tool_registry_validates_arguments():
    with pytest.raises(ValidationError):
        build_mock_registry().execute("compare_periods", {"metric": "secret_metric"})


def test_business_impact_rejects_model_supplied_numbers():
    with pytest.raises(ValidationError):
        build_mock_registry().execute(
            "calculate_business_impact",
            {"metric": "revenue", "current_value": 1, "expected_value": 999999},
        )
