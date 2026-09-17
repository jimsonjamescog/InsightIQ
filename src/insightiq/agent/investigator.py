from __future__ import annotations

import logging
import time
from collections.abc import Callable

from insightiq.agent.providers import DecisionProvider
from insightiq.models import (
    ConfidenceBreakdown,
    EvidenceFinding,
    Hypothesis,
    HypothesisStatus,
    InvestigationEvent,
    InvestigationOutcome,
    InvestigationPriority,
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
ProgressCallback = Callable[[InvestigationState], None]


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

    def create_state(
        self, question: str, investigation_id: str | None = None
    ) -> InvestigationState:
        state = InvestigationState(
            investigation_id=investigation_id or new_id("inv"),
            question=question,
        )
        self.provider.initialize(state, self.registry)
        self._record_event(
            state,
            "HYPOTHESES_GENERATED",
            f"Generated {len(state.hypotheses)} question-specific competing hypotheses.",
        )
        return state

    def investigate(
        self,
        question: str,
        *,
        state: InvestigationState | None = None,
        progress_callback: ProgressCallback | None = None,
        step_delay: float = 0,
    ) -> tuple[InvestigationState, InvestigationReport]:
        started = time.perf_counter()
        state = state or self.create_state(question)
        self._publish(state, progress_callback, step_delay)
        logger.info("investigation_started", extra={"investigation_id": state.investigation_id})

        proposal = None
        seen_requests: dict[str, int] = {}
        while state.steps_taken < self.max_steps:
            state.steps_taken += 1
            decision = self.provider.decide(state, self.registry)
            if decision.final_proposal:
                proposal = decision.final_proposal
                break
            if not decision.tool_request or state.tool_calls >= self.max_tool_calls:
                break

            state.current_intent = decision.investigation_intent
            self._record_event(
                state,
                "EVIDENCE_SEEKING",
                decision.reasoning_summary,
                intent=decision.investigation_intent,
                hypothesis_id=(
                    decision.investigation_intent.hypothesis_id
                    if decision.investigation_intent
                    else None
                ),
                tool_name=decision.tool_request.name,
            )
            self._publish(state, progress_callback, step_delay)

            signature = (
                f"{decision.tool_request.name}:{sorted(decision.tool_request.arguments.items())}"
            )
            seen_requests[signature] = seen_requests.get(signature, 0) + 1
            if seen_requests[signature] > 2:
                break

            result = self.registry.execute(
                decision.tool_request.name,
                decision.tool_request.arguments,
            )
            state.tool_calls += 1
            state.tool_results.append(result)
            self._satisfy_requirement(state, decision.investigation_intent, result.tool_name)
            findings = self.registry.interpret(result)
            if not findings:
                findings = [
                    EvidenceFinding(
                        statement=f"{result.tool_name} returned a traceable result.",
                        evidence_type="HISTORICAL",
                        strength=0.5,
                    )
                ]
            for finding in findings:
                supports, contradicts = self._match_hypotheses(state, finding)
                evidence = self.evidence_store.from_finding(
                    result,
                    finding,
                    supports=supports,
                    contradicts=contradicts,
                )
                state.evidence.append(evidence)
                state.observations.append(evidence.statement)
                self._record_event(
                    state,
                    "EVIDENCE_OBSERVED",
                    evidence.statement,
                    evidence_id=evidence.evidence_id,
                    tool_name=result.tool_name,
                )
            if any(item.evidence_type.value == "BUSINESS_IMPACT" for item in findings):
                state.business_impact = result.result
            self._recalculate_hypotheses(state)
            self._record_event(
                state,
                "HYPOTHESES_UPDATED",
                "Recalculated evidence support scores and hypothesis states.",
            )
            self._publish(state, progress_callback, step_delay)

        if proposal:
            state.root_cause_chain = proposal.root_cause_chain
            state.recommendation = proposal.recommendation
        target_hypothesis_id = proposal.hypothesis_id if proposal else None
        state.confidence = calculate_confidence(
            state.evidence,
            state.root_cause_chain,
            target_hypothesis_id,
        )
        state.evidence_gate = evaluate_gate(
            state.evidence,
            state.confidence,
            self.evidence_store,
            state.root_cause_chain,
            state.business_impact,
            target_hypothesis_id,
            self.confidence_threshold,
            hypotheses=state.hypotheses,
            impact_required=any(
                item.capability == "calculate_impact"
                for items in state.evidence_requirements.values()
                for item in items
            ),
        )

        if proposal and state.evidence_gate.passed:
            state.conclusion = proposal.conclusion
            state.status = InvestigationStatus.COMPLETED
            state.outcome = InvestigationOutcome.ROOT_CAUSE_ESTABLISHED
            self._hypothesis(state, proposal.hypothesis_id).status = HypothesisStatus.SUPPORTED
        else:
            state.conclusion = "Root cause not established"
            state.status = InvestigationStatus.INSUFFICIENT_EVIDENCE
            state.outcome = InvestigationOutcome.INSUFFICIENT_EVIDENCE
            for hypothesis in state.hypotheses:
                if hypothesis.status in {HypothesisStatus.NEW, HypothesisStatus.INVESTIGATING}:
                    hypothesis.status = HypothesisStatus.INSUFFICIENT_EVIDENCE
        state.current_intent = None
        self._record_event(
            state,
            "EVIDENCE_GATE_DECIDED",
            (
                "Evidence Gate established the root cause."
                if state.evidence_gate.passed
                else "Evidence Gate stopped the investigation without establishing a root cause."
            ),
        )
        self._publish(state, progress_callback, 0)

        duration_ms = int((time.perf_counter() - started) * 1000)
        report = self._build_report(state, duration_ms)
        return state, report

    @staticmethod
    def _publish(
        state: InvestigationState,
        callback: ProgressCallback | None,
        delay: float,
    ) -> None:
        if callback:
            callback(state.model_copy(deep=True))
        if delay:
            time.sleep(delay)

    @staticmethod
    def _record_event(
        state: InvestigationState,
        event_type: str,
        message: str,
        **kwargs,
    ) -> None:
        state.events.append(
            InvestigationEvent(
                sequence=len(state.events) + 1,
                event_type=event_type,
                message=message,
                **kwargs,
            )
        )

    @staticmethod
    def _satisfy_requirement(state: InvestigationState, intent, tool_name: str) -> None:
        owner = intent.hypothesis_id if intent and intent.hypothesis_id else "__question__"
        candidates = state.evidence_requirements.get(owner, [])
        requirement = next(
            (item for item in candidates if not item.satisfied and item.tool_name == tool_name),
            None,
        )
        if requirement:
            requirement.satisfied = True

    @staticmethod
    def _match_hypotheses(
        state: InvestigationState,
        finding: EvidenceFinding,
    ) -> tuple[list[str], list[str]]:
        supports: list[str] = []
        contradicts: list[str] = []
        for hypothesis in state.hypotheses:
            if hypothesis.hypothesis_type in finding.supports_types:
                supports.append(hypothesis.hypothesis_id)
            if hypothesis.hypothesis_type in finding.contradicts_types:
                contradicts.append(hypothesis.hypothesis_id)
        if "anomaly" in finding.supports_types or "business_impact" in finding.supports_types:
            supports.extend(
                item.hypothesis_id for item in state.hypotheses if item.parent_hypothesis_id is None
            )
        return list(dict.fromkeys(supports)), list(dict.fromkeys(contradicts))

    @staticmethod
    def _recalculate_hypotheses(state: InvestigationState) -> None:
        for hypothesis in state.hypotheses:
            supporting = [
                item for item in state.evidence if hypothesis.hypothesis_id in item.supports
            ]
            contradicting = [
                item for item in state.evidence if hypothesis.hypothesis_id in item.contradicts
            ]
            hypothesis.supporting_evidence_ids = [item.evidence_id for item in supporting]
            hypothesis.contradicting_evidence_ids = [item.evidence_id for item in contradicting]
            hypothesis.support_score = round(
                max(
                    0,
                    min(
                        100,
                        15
                        + sum(item.strength * 45 for item in supporting)
                        - sum(item.strength * 60 for item in contradicting),
                    ),
                ),
                1,
            )
            requirements = state.evidence_requirements.get(hypothesis.hypothesis_id, [])
            required_evidence_collected = bool(requirements) and all(
                item.satisfied or item.unavailable for item in requirements
            )
            has_specific_support = any(
                hypothesis.hypothesis_type in item.signal_types for item in supporting
            )
            hypothesis.next_evidence_needed = [
                item.description
                for item in requirements
                if not item.satisfied and not item.unavailable
            ]
            strong_contradiction = next(
                (item for item in contradicting if item.strength >= 0.8), None
            )
            if strong_contradiction:
                hypothesis.status = HypothesisStatus.REJECTED
                hypothesis.rejection_reason = strong_contradiction.statement
            elif (
                hypothesis.support_score >= 65
                and len(supporting) >= 2
                and required_evidence_collected
                and has_specific_support
            ):
                hypothesis.status = HypothesisStatus.SUPPORTED
            elif required_evidence_collected:
                hypothesis.status = HypothesisStatus.INSUFFICIENT_EVIDENCE
            elif supporting:
                hypothesis.status = HypothesisStatus.INVESTIGATING
            else:
                hypothesis.status = HypothesisStatus.NEW
            if hypothesis.status in {
                HypothesisStatus.REJECTED,
                HypothesisStatus.INSUFFICIENT_EVIDENCE,
            }:
                hypothesis.investigation_priority = InvestigationPriority.LOW
            elif hypothesis.status in {
                HypothesisStatus.SUPPORTED,
                HypothesisStatus.INVESTIGATING,
            }:
                hypothesis.investigation_priority = InvestigationPriority.HIGH
            else:
                hypothesis.investigation_priority = InvestigationPriority.MEDIUM

    @staticmethod
    def _hypothesis(state: InvestigationState, hypothesis_id: str) -> Hypothesis:
        return next(item for item in state.hypotheses if item.hypothesis_id == hypothesis_id)

    @staticmethod
    def _build_report(state: InvestigationState, duration_ms: int) -> InvestigationReport:
        confidence = state.confidence or ConfidenceBreakdown(
            evidence_strength=0, coverage=0, consistency=0, overall=0
        )
        assert state.evidence_gate is not None
        assert state.outcome is not None
        return InvestigationReport(
            investigation_id=state.investigation_id,
            question=state.question,
            observations=state.observations,
            hypotheses=state.hypotheses,
            follow_up_questions=state.follow_up_questions,
            events=state.events,
            rejected_hypotheses=[
                item for item in state.hypotheses if item.status == HypothesisStatus.REJECTED
            ],
            evidence=state.evidence,
            supporting_evidence=[item for item in state.evidence if item.supports],
            conclusions=[state.conclusion or "Root cause not established"],
            root_cause_chain=state.root_cause_chain if state.evidence_gate.passed else [],
            business_impact=state.business_impact,
            confidence=confidence,
            evidence_gate=state.evidence_gate,
            outcome=state.outcome,
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
