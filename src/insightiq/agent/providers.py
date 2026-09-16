from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI

from insightiq.models import (
    AgentDecision,
    EvidenceClassification,
    FinalProposal,
    InvestigationState,
    RootCauseLink,
    ToolRequest,
)
from insightiq.tools.registry import ToolRegistry, strict_json_schema


class DecisionProvider(ABC):
    @abstractmethod
    def decide(self, state: InvestigationState, registry: ToolRegistry) -> AgentDecision:
        raise NotImplementedError


class DeterministicDecisionProvider(DecisionProvider):
    """A reproducible investigator for demos, tests, and offline development."""

    sequence = [
        ToolRequest(name="compare_periods", arguments={"metric": "revenue"}),
        ToolRequest(name="segment_metric", arguments={"metric": "revenue", "dimension": "region"}),
        ToolRequest(name="compare_periods", arguments={"metric": "traffic"}),
        ToolRequest(name="compare_periods", arguments={"metric": "payment_failure_rate"}),
        ToolRequest(name="check_data_quality", arguments={"field": "customer_region"}),
        ToolRequest(name="get_deployments", arguments={}),
        ToolRequest(name="inspect_schema_changes", arguments={"object_name": "customer_dimension"}),
        ToolRequest(name="get_dependencies", arguments={"object_name": "daily_revenue"}),
        ToolRequest(
            name="calculate_business_impact",
            arguments={"metric": "revenue"},
        ),
    ]

    def decide(self, state: InvestigationState, registry: ToolRegistry) -> AgentDecision:
        called = [result.tool_name for result in state.tool_results]
        for request in self.sequence:
            same_name_count = called.count(request.name)
            required_occurrence = sum(
                1
                for item in self.sequence[: self.sequence.index(request)]
                if item.name == request.name
            )
            if same_name_count <= required_occurrence:
                return AgentDecision(
                    reasoning_summary=f"Collecting the next missing fact with {request.name}.",
                    tool_request=request,
                )
        proposal = _build_proposal(state)
        return AgentDecision(
            reasoning_summary=(
                "The collected values support a causal proposal."
                if proposal
                else "No hypothesis has enough non-conflicting evidence to establish a cause."
            ),
            final_proposal=proposal,
        )


class OpenAIDecisionProvider(DecisionProvider):
    """Responses API provider that lets one model select only allowlisted custom tools."""

    def __init__(self, model: str, client: OpenAI | None = None) -> None:
        self.model = model
        self.client = client or OpenAI()

    def decide(self, state: InvestigationState, registry: ToolRegistry) -> AgentDecision:
        finish_schema = strict_json_schema(FinalProposal)
        finish_tool = {
            "type": "function",
            "name": "finish_investigation",
            "description": (
                "Propose a conclusion only after the required causal evidence is present."
            ),
            "parameters": finish_schema,
            "strict": True,
        }
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "You are InsightIQ, a cautious business investigator. Select exactly one "
                "custom tool per turn. Never invent facts, calculations, evidence IDs, "
                "query IDs, or sources. Investigate competing traffic, payment, "
                "business-segment, and data-quality causes. Use finish_investigation only "
                "when the state contains direct evidence for a complete causal chain and "
                "deterministic business impact. Every root-cause link must cite real evidence "
                "IDs from the supplied state and label itself OBSERVED or INFERRED."
            ),
            input=json.dumps(_state_for_model(state), default=str),
            tools=[*registry.openai_tools(), finish_tool],
            tool_choice="required",
            parallel_tool_calls=False,
            store=False,
        )
        usage = getattr(response, "usage", None)
        state.model_calls += 1
        if usage:
            state.input_tokens += getattr(usage, "input_tokens", 0) or 0
            state.output_tokens += getattr(usage, "output_tokens", 0) or 0

        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if len(calls) != 1:
            raise RuntimeError("The investigator must return exactly one function call.")
        call = calls[0]
        arguments: dict[str, Any] = json.loads(call.arguments)
        if call.name == "finish_investigation":
            return AgentDecision(
                reasoning_summary="The model proposed a final evidence-grounded conclusion.",
                final_proposal=FinalProposal.model_validate(arguments),
            )
        if call.name not in registry.names:
            raise RuntimeError(f"The model selected a non-allowlisted tool: {call.name}")
        return AgentDecision(
            reasoning_summary=f"The model selected {call.name} to gather missing evidence.",
            tool_request=ToolRequest(name=call.name, arguments=arguments),
        )


def _state_for_model(state: InvestigationState) -> dict[str, Any]:
    return {
        "question": state.question,
        "steps_taken": state.steps_taken,
        "hypotheses": [hypothesis.model_dump(mode="json") for hypothesis in state.hypotheses],
        "evidence": [evidence.model_dump(mode="json") for evidence in state.evidence],
        "tool_results": [result.model_dump(mode="json") for result in state.tool_results],
        "business_impact": state.business_impact,
    }


def _result(
    state: InvestigationState, tool: str, metric: str | None = None
) -> dict[str, Any] | None:
    for item in reversed(state.tool_results):
        if item.tool_name == tool and (metric is None or item.result.get("metric") == metric):
            return item.result
    return None


def _evidence_id(state: InvestigationState, tool: str, metric: str | None = None) -> str:
    for item in reversed(state.evidence):
        if item.tool_name == tool:
            result = next(
                result for result in state.tool_results if result.execution_id == item.execution_id
            )
            if metric is None or result.result.get("metric") == metric:
                return item.evidence_id
    raise ValueError(f"Missing evidence for {tool}:{metric or '*'}")


def _link(
    sequence: int,
    statement: str,
    classification: EvidenceClassification,
    evidence_ids: list[str],
) -> RootCauseLink:
    return RootCauseLink(
        link_id=f"cause-{sequence}",
        sequence=sequence,
        statement=statement,
        classification=classification,
        evidence_ids=evidence_ids,
    )


def _build_proposal(state: InvestigationState) -> FinalProposal | None:
    revenue = _result(state, "compare_periods", "revenue") or {}
    payment = _result(state, "compare_periods", "payment_failure_rate") or {}
    quality = _result(state, "check_data_quality") or {}
    deployments = (_result(state, "get_deployments") or {}).get("deployments", [])
    changes = (_result(state, "inspect_schema_changes") or {}).get("changes", [])
    dependencies = _result(state, "get_dependencies") or {}
    impact = _result(state, "calculate_business_impact") or {}

    payment_is_cause = (
        revenue.get("percent_change", 0) <= -20
        and payment.get("current_value", 0) >= 0.05
        and payment.get("current_value", 0) >= payment.get("baseline_value", 0) * 3
        and impact.get("understatement", 0) > 0
    )
    if payment_is_cause:
        revenue_id = _evidence_id(state, "compare_periods", "revenue")
        payment_id = _evidence_id(state, "compare_periods", "payment_failure_rate")
        impact_id = _evidence_id(state, "calculate_business_impact")
        return FinalProposal(
            hypothesis_id="H2",
            conclusion=(
                "A material increase in payment failures reduced completed orders and caused "
                "the revenue decline."
            ),
            root_cause_chain=[
                _link(
                    1,
                    "Payment failure rate increased materially above its historical baseline.",
                    EvidenceClassification.OBSERVED,
                    [payment_id],
                ),
                _link(
                    2,
                    "The elevated failures prevented affected checkouts from becoming paid orders.",
                    EvidenceClassification.INFERRED,
                    [payment_id, revenue_id],
                ),
                _link(
                    3,
                    "Completed reported revenue fell relative to its baseline.",
                    EvidenceClassification.OBSERVED,
                    [revenue_id],
                ),
                _link(
                    4,
                    "The missing paid orders account for the calculated business impact.",
                    EvidenceClassification.INFERRED,
                    [payment_id, revenue_id, impact_id],
                ),
            ],
            recommendation=(
                "Escalate the payment provider failure, restore successful authorization rates, "
                "and recover affected customer checkouts."
            ),
        )

    relevant_deployment = any(item.get("service") == "customer-transform" for item in deployments)
    data_is_cause = (
        revenue.get("percent_change", 0) <= -20
        and quality.get("anomaly") is True
        and relevant_deployment
        and bool(changes)
        and bool(dependencies.get("filter_logic"))
        and impact.get("understatement", 0) > 0
    )
    if not data_is_cause:
        return None
    revenue_id = _evidence_id(state, "compare_periods", "revenue")
    quality_id = _evidence_id(state, "check_data_quality")
    deployment_id = _evidence_id(state, "get_deployments")
    schema_id = _evidence_id(state, "inspect_schema_changes")
    dependency_id = _evidence_id(state, "get_dependencies")
    impact_id = _evidence_id(state, "calculate_business_impact")
    return FinalProposal(
        hypothesis_id="H4",
        conclusion=(
            "A customer-region transformation regression caused valid transactions to be "
            "excluded from reporting; the decline is a reporting understatement, not a "
            "corresponding demand collapse."
        ),
        root_cause_chain=[
            _link(
                1,
                "The customer-region null rate increased sharply above its baseline.",
                EvidenceClassification.OBSERVED,
                [quality_id],
            ),
            _link(
                2,
                "Deployment deploy-284 changed the customer-region mapping at the anomaly onset.",
                EvidenceClassification.OBSERVED,
                [deployment_id, schema_id],
            ),
            _link(
                3,
                "The revenue model excludes transactions whose customer region is null.",
                EvidenceClassification.OBSERVED,
                [dependency_id],
            ),
            _link(
                4,
                "The mapping regression caused the measured reporting understatement.",
                EvidenceClassification.INFERRED,
                [revenue_id, quality_id, schema_id, dependency_id, impact_id],
            ),
        ],
        recommendation=(
            "Roll back or correct deployment deploy-284, backfill customer_region, rerun the "
            "revenue models, and add a null-rate deployment gate for critical dimensions."
        ),
    )
