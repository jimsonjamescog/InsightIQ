from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class EvidenceClassification(StrEnum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"


class EvidenceType(StrEnum):
    STATISTICAL = "STATISTICAL"
    TEMPORAL = "TEMPORAL"
    DEPENDENCY = "DEPENDENCY"
    HISTORICAL = "HISTORICAL"
    BUSINESS_IMPACT = "BUSINESS_IMPACT"


class InvestigationPriority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class InvestigationOutcome(StrEnum):
    ROOT_CAUSE_ESTABLISHED = "ROOT_CAUSE_ESTABLISHED"
    PROBABLE_ROOT_CAUSE = "PROBABLE_ROOT_CAUSE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class HypothesisStatus(StrEnum):
    NEW = "NEW"
    INVESTIGATING = "INVESTIGATING"
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class InvestigationStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class Hypothesis(BaseModel):
    hypothesis_id: str
    description: str
    hypothesis_type: str
    question: str
    parent_hypothesis_id: str | None = None
    status: HypothesisStatus = HypothesisStatus.NEW
    support_score: float = Field(default=20, ge=0, le=100)
    investigation_priority: InvestigationPriority = InvestigationPriority.MEDIUM
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    next_evidence_needed: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None
    follow_up_question: str | None = None

    @property
    def supporting_evidence(self) -> list[str]:
        return self.supporting_evidence_ids

    @property
    def contradicting_evidence(self) -> list[str]:
        return self.contradicting_evidence_ids


class ToolResult(BaseModel):
    tool_name: str
    execution_id: str
    query_id: str
    source: str
    timestamp: datetime = Field(default_factory=utc_now)
    success: bool = True
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any]
    error: str | None = None


class Evidence(BaseModel):
    evidence_id: str
    classification: EvidenceClassification
    evidence_type: EvidenceType = EvidenceType.STATISTICAL
    observation_type: str
    statement: str
    tool_name: str | None = None
    execution_id: str | None = None
    query_id: str | None = None
    source: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    signal_types: list[str] = Field(default_factory=list)
    strength: float = Field(default=0.5, ge=0, le=1)


class RootCauseLink(BaseModel):
    link_id: str
    sequence: int = Field(ge=1)
    statement: str
    classification: EvidenceClassification
    evidence_ids: list[str] = Field(min_length=1)


class ConfidenceBreakdown(BaseModel):
    evidence_strength: float
    coverage: float
    consistency: float
    overall: float


class EvidenceGateResult(BaseModel):
    passed: bool
    confidence: float
    reasons: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class EvidenceRequirement(BaseModel):
    requirement_id: str
    capability: str
    description: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    information_value: float = Field(default=0.5, ge=0, le=1)
    satisfied: bool = False
    unavailable: bool = False
    tool_name: str | None = None


class EvidenceFinding(BaseModel):
    statement: str
    evidence_type: EvidenceType
    supports_types: list[str] = Field(default_factory=list)
    contradicts_types: list[str] = Field(default_factory=list)
    strength: float = Field(default=0.5, ge=0, le=1)


class InvestigationIntent(BaseModel):
    question: str
    hypothesis_id: str | None = None
    hypothesis: str | None = None
    evidence_sought: str
    selected_tool: str | None = None
    reason: str


class InvestigationEvent(BaseModel):
    sequence: int
    event_type: str
    message: str
    intent: InvestigationIntent | None = None
    hypothesis_id: str | None = None
    evidence_id: str | None = None
    tool_name: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class InvestigationStatistics(BaseModel):
    steps: int
    tool_calls: int
    duration_ms: int
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class InvestigationState(BaseModel):
    investigation_id: str
    question: str
    observations: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_requirements: dict[str, list[EvidenceRequirement]] = Field(default_factory=dict)
    follow_up_questions: list[str] = Field(default_factory=list)
    current_intent: InvestigationIntent | None = None
    events: list[InvestigationEvent] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    steps_taken: int = 0
    tool_calls: int = 0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    status: InvestigationStatus = InvestigationStatus.RUNNING
    outcome: InvestigationOutcome | None = None
    conclusion: str | None = None
    root_cause_chain: list[RootCauseLink] = Field(default_factory=list)
    business_impact: dict[str, Any] = Field(default_factory=dict)
    recommendation: str | None = None
    confidence: ConfidenceBreakdown | None = None
    evidence_gate: EvidenceGateResult | None = None


class InvestigationReport(BaseModel):
    investigation_id: str
    question: str
    observations: list[str]
    hypotheses: list[Hypothesis]
    follow_up_questions: list[str]
    events: list[InvestigationEvent]
    rejected_hypotheses: list[Hypothesis]
    evidence: list[Evidence]
    supporting_evidence: list[Evidence]
    conclusions: list[str]
    root_cause_chain: list[RootCauseLink]
    business_impact: dict[str, Any]
    confidence: ConfidenceBreakdown
    evidence_gate: EvidenceGateResult
    outcome: InvestigationOutcome
    recommendation: str
    statistics: InvestigationStatistics


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str


class GraphExport(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ToolRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class FinalProposal(BaseModel):
    hypothesis_id: str
    conclusion: str
    root_cause_chain: list[RootCauseLink]
    recommendation: str


class AgentDecision(BaseModel):
    reasoning_summary: str
    investigation_intent: InvestigationIntent | None = None
    tool_request: ToolRequest | None = None
    final_proposal: FinalProposal | None = None
