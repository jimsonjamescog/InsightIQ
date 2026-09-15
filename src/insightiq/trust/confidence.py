from __future__ import annotations

from insightiq.models import ConfidenceBreakdown, Evidence, EvidenceGateResult
from insightiq.trust.evidence import EvidenceStore

REQUIRED_CHAIN_TOOLS = {
    "check_data_quality",
    "get_deployments",
    "inspect_schema_changes",
    "get_dependencies",
    "calculate_business_impact",
}


def calculate_confidence(evidence: list[Evidence]) -> ConfidenceBreakdown:
    supporting = [item for item in evidence if item.supports]
    strength = sum(item.strength for item in supporting) / len(supporting) if supporting else 0.0
    available = {item.tool_name for item in evidence if item.tool_name}
    coverage = len(available & REQUIRED_CHAIN_TOOLS) / len(REQUIRED_CHAIN_TOOLS)
    contradictory = sum(1 for item in evidence if item.contradicts and item.supports)
    consistency = max(0.0, 1.0 - contradictory / max(1, len(evidence)))
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
    root_cause_chain: list[str],
    business_impact: dict,
    threshold: float = 0.75,
) -> EvidenceGateResult:
    reasons: list[str] = []
    missing: list[str] = []
    provenance_valid, provenance_errors = evidence_store.validate_all(evidence)
    support_count = sum(1 for item in evidence if item.supports)

    if confidence.overall < threshold:
        missing.append(f"Confidence {confidence.overall:.2f} is below threshold {threshold:.2f}.")
    if support_count < 2:
        missing.append("At least two supporting observed evidence items are required.")
    if not provenance_valid:
        missing.extend(provenance_errors)
    if len(root_cause_chain) < 4:
        missing.append("The proposed causal chain has fewer than four supported links.")
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
