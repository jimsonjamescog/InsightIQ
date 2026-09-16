from __future__ import annotations

from insightiq.models import (
    ConfidenceBreakdown,
    Evidence,
    EvidenceClassification,
    EvidenceGateResult,
    RootCauseLink,
)
from insightiq.trust.evidence import EvidenceStore


def calculate_confidence(
    evidence: list[Evidence],
    root_cause_chain: list[RootCauseLink] | None = None,
    target_hypothesis_id: str | None = None,
) -> ConfidenceBreakdown:
    chain = root_cause_chain or []
    evidence_by_id = {item.evidence_id: item for item in evidence}
    referenced_ids = {evidence_id for link in chain for evidence_id in link.evidence_ids}
    referenced = [evidence_by_id[item] for item in referenced_ids if item in evidence_by_id]
    strength = sum(item.strength for item in referenced) / len(referenced) if referenced else 0.0
    covered_links = sum(
        1
        for link in chain
        if link.evidence_ids and all(item in evidence_by_id for item in link.evidence_ids)
    )
    coverage = covered_links / len(chain) if chain else 0.0
    has_target_conflict = bool(
        target_hypothesis_id and any(target_hypothesis_id in item.contradicts for item in evidence)
    )
    consistency = 0.0 if has_target_conflict else 1.0
    overall = strength * 0.4 + coverage * 0.35 + consistency * 0.25
    return ConfidenceBreakdown(
        evidence_strength=round(strength, 3),
        coverage=round(coverage, 3),
        consistency=round(consistency, 3),
        overall=round(overall, 3),
    )


def evaluate_gate(
    evidence: list[Evidence],
    confidence: ConfidenceBreakdown,
    evidence_store: EvidenceStore,
    root_cause_chain: list[RootCauseLink],
    business_impact: dict,
    target_hypothesis_id: str | None = None,
    threshold: float = 0.75,
) -> EvidenceGateResult:
    reasons: list[str] = []
    missing: list[str] = []
    provenance_valid, provenance_errors = evidence_store.validate_all(evidence)
    support_count = sum(
        1 for item in evidence if target_hypothesis_id and target_hypothesis_id in item.supports
    )
    evidence_by_id = {item.evidence_id: item for item in evidence}

    if confidence.overall < threshold:
        missing.append(f"Confidence {confidence.overall:.2f} is below threshold {threshold:.2f}.")
    if support_count < 2:
        missing.append("At least two supporting observed evidence items are required.")
    if target_hypothesis_id and any(target_hypothesis_id in item.contradicts for item in evidence):
        missing.append("Unresolved evidence contradicts the proposed root-cause hypothesis.")
    if not provenance_valid:
        missing.extend(provenance_errors)
    if len(root_cause_chain) < 4:
        missing.append("The proposed causal chain has fewer than four supported links.")
    expected_sequence = list(range(1, len(root_cause_chain) + 1))
    if [link.sequence for link in root_cause_chain] != expected_sequence:
        missing.append("Root-cause links are not in a complete contiguous sequence.")
    for link in root_cause_chain:
        missing_ids = [item for item in link.evidence_ids if item not in evidence_by_id]
        if missing_ids:
            missing.append(
                f"Root-cause link {link.link_id} cites unknown evidence: {', '.join(missing_ids)}."
            )
        if link.classification == EvidenceClassification.OBSERVED and any(
            evidence_by_id[item].classification != EvidenceClassification.OBSERVED
            for item in link.evidence_ids
            if item in evidence_by_id
        ):
            missing.append(f"Observed root-cause link {link.link_id} cites inferred evidence.")
        if target_hypothesis_id and not any(
            target_hypothesis_id in evidence_by_id[item].supports
            for item in link.evidence_ids
            if item in evidence_by_id
        ):
            missing.append(
                f"Root-cause link {link.link_id} has no evidence supporting "
                f"{target_hypothesis_id}."
            )
    if not business_impact:
        missing.append("Business impact has not been calculated deterministically.")

    if not missing:
        reasons.extend(
            [
                "Confidence meets the configured threshold.",
                "Multiple observed evidence items support the conclusion.",
                "All observed evidence has valid tool provenance.",
                "The causal chain and business impact are complete.",
            ]
        )
    return EvidenceGateResult(
        passed=not missing,
        confidence=confidence.overall,
        reasons=reasons,
        missing_evidence=missing,
    )
