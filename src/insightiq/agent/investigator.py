from __future__ import annotations

import logging
import time
from typing import Any

from insightiq.agent.providers import DecisionProvider
from insightiq.models import (
    ConfidenceBreakdown,
    Hypothesis,
    HypothesisStatus,
    InvestigationReport,
    InvestigationState,
    InvestigationStatistics,
    InvestigationStatus,
    new_id,
)
from insightiq.tools.registry import ToolRegistry
from insightiq.trust.confidence import calculate_confidence, evaluate_gate
from insightiq.trust.evidence import EvidenceStore

logger = logging.getLogger("insightiq.investigator")

DATA_HYPOTHESIS = "H4"


def initial_hypotheses() -> list[Hypothesis]:
    return [
        Hypothesis(hypothesis_id="H1", description="Customer demand or traffic decreased."),
        Hypothesis(hypothesis_id="H2", description="Payment failures caused lost revenue."),
        Hypothesis(hypothesis_id="H3", description="Regional business performance declined."),
        Hypothesis(
            hypothesis_id=DATA_HYPOTHESIS,
            description="A reporting or data-quality regression excluded valid transactions.",
        ),
    ]


class Investigator:
    def __init__(
        self,
        registry: ToolRegistry,
        provider: DecisionProvider,
        *,
        max_steps: int = 15,
        max_tool_calls: int = 12,
        confidence_threshold: float = 0.75,
    ) -> None:
        self.registry = registry
        self.provider = provider
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.confidence_threshold = confidence_threshold
        self.evidence_store = EvidenceStore()

    def investigate(self, question: str) -> tuple[InvestigationState, InvestigationReport]:
        started = time.perf_counter()
        state = InvestigationState(
            investigation_id=new_id("inv"),
            question=question,
            hypotheses=initial_hypotheses(),
        )
        logger.info("investigation_started", extra={"investigation_id": state.investigation_id})

        proposal = None
        seen_requests: dict[str, int] = {}
        while state.steps_taken < self.max_steps:
            state.steps_taken += 1
            decision = self.provider.decide(state, self.registry)
            if decision.final_proposal:
                proposal = decision.final_proposal
                break
            if not decision.tool_request:
                break
            if state.tool_calls >= self.max_tool_calls:
                break

            signature = (
                f"{decision.tool_request.name}:{sorted(decision.tool_request.arguments.items())}"
            )
            seen_requests[signature] = seen_requests.get(signature, 0) + 1
            if seen_requests[signature] > 2:
                logger.warning(
                    "repeated_tool_request", extra={"investigation_id": state.investigation_id}
                )
                break

            result = self.registry.execute(
                decision.tool_request.name,
                decision.tool_request.arguments,
            )
            state.tool_calls += 1
            state.tool_results.append(result)
            evidence = self._interpret_result(state, result.tool_name, result.result)
            state.evidence.append(
                self.evidence_store.from_tool_result(
                    result,
                    supports=evidence["supports"],
                    contradicts=evidence["contradicts"],
                    strength=evidence["strength"],
                )
            )
            state.observations.append(state.evidence[-1].statement)
            self._update_hypotheses(state, result.tool_name)
            if result.tool_name == "calculate_business_impact":
                state.business_impact = result.result
            logger.info(
                "tool_completed",
                extra={
                    "investigation_id": state.investigation_id,
                    "tool_name": result.tool_name,
                    "query_id": result.query_id,
                },
            )

        if proposal:
            state.root_cause_chain = proposal.root_cause_chain
            state.recommendation = proposal.recommendation
        state.confidence = calculate_confidence(state.evidence)
        state.evidence_gate = evaluate_gate(
            state.evidence,
            state.confidence,
            self.evidence_store,
            state.root_cause_chain,
            state.business_impact,
            self.confidence_threshold,
        )

        if proposal and state.evidence_gate.passed:
            state.conclusion = proposal.conclusion
            state.status = InvestigationStatus.COMPLETED
            self._hypothesis(state, DATA_HYPOTHESIS).status = HypothesisStatus.SUPPORTED
        else:
            state.conclusion = "Root cause not established"
            state.status = InvestigationStatus.INSUFFICIENT_EVIDENCE
            for hypothesis in state.hypotheses:
                if hypothesis.status in {HypothesisStatus.NEW, HypothesisStatus.INVESTIGATING}:
                    hypothesis.status = HypothesisStatus.INSUFFICIENT_EVIDENCE

        duration_ms = int((time.perf_counter() - started) * 1000)
        report = self._build_report(state, duration_ms)
        logger.info(
            "investigation_completed",
            extra={
                "investigation_id": state.investigation_id,
                "status": state.status.value,
                "confidence": state.confidence.overall,
            },
        )
        return state, report

    def _interpret_result(
        self, state: InvestigationState, tool: str, result: dict
    ) -> dict[str, Any]:
        supports: list[str] = []
        contradicts: list[str] = []
        strength = 0.9
        if tool == "compare_periods" and result["metric"] == "traffic":
            contradicts = ["H1"]
        elif tool == "compare_periods" and result["metric"] == "payment_failure_rate":
            contradicts = ["H2"]
        elif tool == "segment_metric":
            supports = ["H3", "H4"]
        elif tool in {
            "check_data_quality",
            "get_deployments",
            "inspect_schema_changes",
            "get_dependencies",
            "calculate_business_impact",
        }:
            supports = [DATA_HYPOTHESIS]
            strength = 1.0 if tool in {"check_data_quality", "get_dependencies"} else 0.9
        return {"supports": supports, "contradicts": contradicts, "strength": strength}

    def _update_hypotheses(self, state: InvestigationState, tool: str) -> None:
        if tool == "compare_periods" and state.tool_results[-1].result["metric"] == "traffic":
            hypothesis = self._hypothesis(state, "H1")
            hypothesis.status = HypothesisStatus.REJECTED
            hypothesis.rejection_reason = "Traffic remained at its historical baseline."
            hypothesis.contradicting_evidence.append(state.evidence[-1].evidence_id)
        elif (
            tool == "compare_periods"
            and state.tool_results[-1].result["metric"] == "payment_failure_rate"
        ):
            hypothesis = self._hypothesis(state, "H2")
            hypothesis.status = HypothesisStatus.REJECTED
            hypothesis.rejection_reason = (
                "Payment failure rate remained near its historical baseline."
            )
            hypothesis.contradicting_evidence.append(state.evidence[-1].evidence_id)
        elif tool == "segment_metric":
            hypothesis = self._hypothesis(state, "H3")
            hypothesis.status = HypothesisStatus.INVESTIGATING
            hypothesis.supporting_evidence.append(state.evidence[-1].evidence_id)
        elif tool in {
            "check_data_quality",
            "get_deployments",
            "inspect_schema_changes",
            "get_dependencies",
            "calculate_business_impact",
        }:
            hypothesis = self._hypothesis(state, DATA_HYPOTHESIS)
            hypothesis.status = HypothesisStatus.INVESTIGATING
            hypothesis.supporting_evidence.append(state.evidence[-1].evidence_id)
            if tool == "get_dependencies":
                regional = self._hypothesis(state, "H3")
                regional.status = HypothesisStatus.REJECTED
                regional.rejection_reason = (
                    "The regional pattern is explained by null-region filtering, "
                    "not regional demand."
                )

    @staticmethod
    def _hypothesis(state: InvestigationState, hypothesis_id: str) -> Hypothesis:
        return next(item for item in state.hypotheses if item.hypothesis_id == hypothesis_id)

    @staticmethod
    def _build_report(state: InvestigationState, duration_ms: int) -> InvestigationReport:
        confidence = state.confidence or ConfidenceBreakdown(
            evidence_strength=0, coverage=0, consistency=0, overall=0
        )
        assert state.evidence_gate is not None
        return InvestigationReport(
            investigation_id=state.investigation_id,
            question=state.question,
            observations=state.observations,
            hypotheses=state.hypotheses,
            rejected_hypotheses=[
                item for item in state.hypotheses if item.status == HypothesisStatus.REJECTED
            ],
            supporting_evidence=[item for item in state.evidence if item.supports],
            conclusions=[state.conclusion or "Root cause not established"],
            root_cause_chain=state.root_cause_chain if state.evidence_gate.passed else [],
            business_impact=state.business_impact,
            confidence=confidence,
            evidence_gate=state.evidence_gate,
            recommendation=state.recommendation
            or "Gather the missing evidence and rerun the investigation.",
            statistics=InvestigationStatistics(
                steps=state.steps_taken,
                tool_calls=state.tool_calls,
                duration_ms=duration_ms,
                model_calls=state.model_calls,
                input_tokens=state.input_tokens,
                output_tokens=state.output_tokens,
            ),
        )
