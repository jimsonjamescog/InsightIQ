from pydantic import BaseModel

from insightiq.agent.investigator import Investigator
from insightiq.agent.providers import DeterministicDecisionProvider
from insightiq.models import (
    EvidenceFinding,
    EvidenceType,
    InvestigationOutcome,
    ToolResult,
    new_id,
)
from insightiq.tools import build_mock_registry
from insightiq.tools.registry import ToolDefinition, ToolRegistry


def investigate(question: str):
    return Investigator(build_mock_registry(), DeterministicDecisionProvider()).investigate(
        question
    )


def test_revenue_question_generates_and_investigates_dynamic_hypotheses():
    state, report = investigate("Why did revenue drop yesterday?")
    types = {item.hypothesis_type for item in state.hypotheses}

    assert {"demand_decline", "pricing_issue", "payment_failure", "data_quality_failure"} <= types
    assert report.outcome == InvestigationOutcome.ROOT_CAUSE_ESTABLISHED
    assert any(item.event_type == "EVIDENCE_SEEKING" for item in report.events)


def test_regional_order_question_follows_a_different_path():
    state, _ = investigate("Why did Northeast order volume fall yesterday?")
    types = {item.hypothesis_type for item in state.hypotheses}
    calls = [(item.tool_name, item.arguments) for item in state.tool_results]

    assert "regional_pattern" in types
    assert "pricing_issue" not in types
    assert (
        "compare_periods",
        {"metric": "orders", "current_period": "yesterday", "baseline_period": "previous_28_days"},
    ) in calls
    assert any(name == "segment_metric" and args["metric"] == "orders" for name, args in calls)


def test_data_completeness_question_uses_operational_evidence():
    state, report = investigate("Why did customer region data become incomplete?")
    call_names = {item.tool_name for item in state.tool_results}

    assert {"get_deployments", "get_pipeline_runs", "inspect_schema_changes"} <= call_names
    assert not any(
        item.tool_name == "compare_periods" and item.arguments.get("metric") == "revenue"
        for item in state.tool_results
    )
    assert report.evidence_gate.passed


def test_supported_broad_hypothesis_creates_recursive_question():
    state, _ = investigate("Why did revenue drop yesterday?")

    assert "What caused the customer-region data-quality failure?" in state.follow_up_questions
    assert any(item.parent_hypothesis_id for item in state.hypotheses)
    assert any(item.event_type == "FOLLOW_UP_CREATED" for item in state.events)


def test_unknown_question_returns_insufficient_evidence_without_guessing():
    _, report = investigate("Why did employee happiness change?")

    assert report.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert report.conclusions == ["Root cause not established"]
    assert report.root_cause_chain == []
    assert report.evidence_gate.missing_evidence


class ReplacementInput(BaseModel):
    metric: str


def replacement_handler(args: ReplacementInput) -> ToolResult:
    return ToolResult(
        tool_name="check_metric_replacement",
        execution_id=new_id("exec"),
        query_id="replacement:1",
        source="TEST.METRICS",
        result={"metric": args.metric, "percent_change": -40},
    )


def test_new_tool_is_discovered_without_investigator_changes():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="check_metric_replacement",
            description="Replacement KPI comparison capability.",
            input_model=ReplacementInput,
            handler=replacement_handler,
            output_schema={"type": "object"},
            evidence_types=[EvidenceType.STATISTICAL],
            applicable_domains=["revenue"],
            capabilities=["compare_metric"],
            cost_or_latency_hint="LOW",
            interpreter=lambda result: [
                EvidenceFinding(
                    statement="Revenue declined 40%.",
                    evidence_type=EvidenceType.STATISTICAL,
                    supports_types=["anomaly"],
                    strength=1,
                )
            ],
        )
    )
    provider = DeterministicDecisionProvider()
    investigator = Investigator(registry, provider)
    state = investigator.create_state("Why did revenue drop yesterday?")

    decision = provider.decide(state, registry)

    assert decision.tool_request is not None
    assert decision.tool_request.name == "check_metric_replacement"
