from pathlib import Path

import pytest

from insightiq.agent.investigator import Investigator
from insightiq.agent.providers import DeterministicDecisionProvider
from insightiq.data.warehouse import ScenarioName, build_warehouse
from insightiq.models import EvidenceClassification, HypothesisStatus, InvestigationStatus
from insightiq.tools.warehouse import DuckDBRunner, build_warehouse_registry

QUESTION = "Why did reported revenue decrease yesterday?"


def investigate(path: Path, scenario: ScenarioName):
    build_warehouse(path, reset=True, scenario=scenario)
    registry = build_warehouse_registry(DuckDBRunner(path))
    return Investigator(registry, DeterministicDecisionProvider()).investigate(QUESTION)


def test_repeatedly_recovers_expected_root_cause(tmp_path: Path):
    path = tmp_path / "regression.duckdb"
    build_warehouse(path, scenario=ScenarioName.BASE)
    registry = build_warehouse_registry(DuckDBRunner(path))
    chains = []

    for _ in range(10):
        state, report = Investigator(registry, DeterministicDecisionProvider()).investigate(
            QUESTION
        )
        assert state.status == InvestigationStatus.COMPLETED
        assert report.evidence_gate.passed
        assert "deployment defect" in report.conclusions[0]
        assert report.confidence.overall >= 0.75
        assert all(
            evidence.execution_id and evidence.query_id and evidence.source
            for evidence in report.evidence
            if evidence.classification == EvidenceClassification.OBSERVED
        )
        chains.append([link.statement for link in report.root_cause_chain])

    assert all(chain == chains[0] for chain in chains)


@pytest.mark.parametrize(
    "scenario",
    [
        ScenarioName.MISSING_DEPLOYMENT,
        ScenarioName.CONFLICTING_EVIDENCE,
        ScenarioName.DATA_QUALITY_NO_DEPLOYMENT,
        ScenarioName.INSUFFICIENT_EVIDENCE,
    ],
)
def test_negative_scenarios_do_not_establish_root_cause(tmp_path: Path, scenario: ScenarioName):
    state, report = investigate(tmp_path / f"{scenario}.duckdb", scenario)

    assert state.status == InvestigationStatus.INSUFFICIENT_EVIDENCE
    assert report.conclusions == ["Root cause not established"]
    assert not report.evidence_gate.passed
    assert report.root_cause_chain == []


def test_conflicting_evidence_is_explicitly_rejected(tmp_path: Path):
    state, report = investigate(tmp_path / "conflict.duckdb", ScenarioName.CONFLICTING_EVIDENCE)
    data_hypothesis = next(
        item for item in state.hypotheses if item.hypothesis_type == "data_quality_failure"
    )

    assert data_hypothesis.status == HypothesisStatus.REJECTED
    assert data_hypothesis.supporting_evidence
    assert data_hypothesis.contradicting_evidence
    assert not report.evidence_gate.passed


def test_payment_failure_can_be_the_supported_root_cause(tmp_path: Path):
    state, report = investigate(tmp_path / "payment.duckdb", ScenarioName.PAYMENT_FAILURE)
    statuses = {item.hypothesis_type: item.status for item in state.hypotheses}

    assert state.status == InvestigationStatus.COMPLETED
    assert report.evidence_gate.passed
    assert statuses["payment_failure"] == HypothesisStatus.SUPPORTED
    assert statuses["data_quality_failure"] == HypothesisStatus.REJECTED
    assert "payment failures" in report.conclusions[0]
    assert {link.classification for link in report.root_cause_chain} == {
        EvidenceClassification.OBSERVED,
        EvidenceClassification.INFERRED,
    }


def test_every_root_cause_link_has_valid_evidence(tmp_path: Path):
    _, report = investigate(tmp_path / "traceability.duckdb", ScenarioName.BASE)
    evidence_ids = {item.evidence_id for item in report.evidence}

    assert report.root_cause_chain
    for index, link in enumerate(report.root_cause_chain, start=1):
        assert link.sequence == index
        assert link.evidence_ids
        assert set(link.evidence_ids) <= evidence_ids
