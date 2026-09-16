from insightiq.agent.investigator import Investigator
from insightiq.agent.providers import DeterministicDecisionProvider
from insightiq.models import HypothesisStatus, InvestigationStatus
from insightiq.tools import build_mock_registry
from insightiq.trust.graph import build_graph


def run_investigation():
    return Investigator(build_mock_registry(), DeterministicDecisionProvider()).investigate(
        "Why did reported revenue decrease yesterday?"
    )


def test_end_to_end_investigation_passes_gate():
    state, report = run_investigation()
    assert state.status == InvestigationStatus.COMPLETED
    assert report.evidence_gate.passed
    assert report.business_impact["understatement"] == 48000
    assert report.statistics.tool_calls == 9
    assert len(report.root_cause_chain) == 4


def test_decoys_are_rejected_and_data_hypothesis_supported():
    state, _ = run_investigation()
    statuses = {item.hypothesis_id: item.status for item in state.hypotheses}
    assert statuses["H1"] == HypothesisStatus.REJECTED
    assert statuses["H2"] == HypothesisStatus.REJECTED
    assert statuses["H3"] == HypothesisStatus.REJECTED
    assert statuses["H4"] == HypothesisStatus.SUPPORTED


def test_graph_contains_provenance_and_conclusion():
    state, _ = run_investigation()
    graph = build_graph(state)
    node_types = {node.type for node in graph.nodes}
    edge_types = {edge.type for edge in graph.edges}
    assert {"QUESTION", "HYPOTHESIS", "EVIDENCE", "TOOL_CALL", "CONCLUSION"} <= node_types
    assert {"PRODUCED", "SUPPORTS", "CONTRADICTS", "JUSTIFIES", "SUPPORTS_LINK"} <= edge_types


def test_step_limit_returns_insufficient_evidence():
    state, report = Investigator(
        build_mock_registry(), DeterministicDecisionProvider(), max_steps=2
    ).investigate("Why did reported revenue decrease yesterday?")
    assert state.status == InvestigationStatus.INSUFFICIENT_EVIDENCE
    assert not report.evidence_gate.passed
    assert report.conclusions == ["Root cause not established"]
