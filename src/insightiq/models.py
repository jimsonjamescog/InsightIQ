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
    status: HypothesisStatus = HypothesisStatus.NEW
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    next_evidence_needed: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None


class ToolResult(BaseModel):
    tool_name: str
    execution_id: str
    query_id: str
    source: str
    timestamp: datetime = Field(default_factory=utc_now)
    result: dict[str, Any]
    error: str | None = None


class Evidence(BaseModel):
    evidence_id: str
    classification: EvidenceClassification
    observation_type: str
    statement: str
    tool_name: str | None = None
    execution_id: str | None = None
    query_id: str | None = None
    source: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    strength: float = Field(default=0.5, ge=0, le=1)


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
    tool_results: list[ToolResult] = Field(default_factory=list)
    steps_taken: int = 0
    tool_calls: int = 0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    status: InvestigationStatus = InvestigationStatus.RUNNING
    conclusion: str | None = None
    root_cause_chain: list[str] = Field(default_factory=list)
    business_impact: dict[str, Any] = Field(default_factory=dict)
    recommendation: str | None = None
    confidence: ConfidenceBreakdown | None = None
    evidence_gate: EvidenceGateResult | None = None


class InvestigationReport(BaseModel):
    investigation_id: str
    question: str
    observations: list[str]
    hypotheses: list[Hypothesis]
    rejected_hypotheses: list[Hypothesis]
    supporting_evidence: list[Evidence]
    conclusions: list[str]
    root_cause_chain: list[str]
    business_impact: dict[str, Any]
    confidence: ConfidenceBreakdown
    evidence_gate: EvidenceGateResult
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
    conclusion: str
    root_cause_chain: list[str]
    recommendation: str


class AgentDecision(BaseModel):
    reasoning_summary: str
    tool_request: ToolRequest | None = None
    final_proposal: FinalProposal | None = None
