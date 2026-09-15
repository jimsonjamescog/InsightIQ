from insightiq.models import Evidence, EvidenceClassification, ToolResult, new_id
from insightiq.trust.confidence import calculate_confidence, evaluate_gate
from insightiq.trust.evidence import EvidenceStore


def test_observed_evidence_requires_real_execution():
    store = EvidenceStore()
    evidence = Evidence(
        evidence_id="e-1",
        classification=EvidenceClassification.OBSERVED,
        observation_type="test",
        statement="Unbacked statement",
        tool_name="compare_periods",
        execution_id="missing",
        query_id="q-1",
        source="table",
    )
    valid, errors = store.validate(evidence)
    assert not valid
    assert errors


def test_evidence_from_execution_is_traceable():
    store = EvidenceStore()
    result = ToolResult(
        tool_name="compare_periods",
        execution_id=new_id("exec"),
        query_id="query-1",
        source="daily_kpis",
        result={
            "metric": "revenue",
            "percent_change": -40,
            "baseline_value": 100,
            "current_value": 60,
            "unit": "USD",
        },
    )
    evidence = store.from_tool_result(result, supports=["H1"])
    assert store.validate(evidence) == (True, [])


def test_gate_fails_without_causal_chain():
    store = EvidenceStore()
    confidence = calculate_confidence([])
    gate = evaluate_gate([], confidence, store, [], {}, threshold=0.75)
    assert not gate.passed
    assert gate.missing_evidence
