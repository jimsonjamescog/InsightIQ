from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI

from insightiq.models import AgentDecision, FinalProposal, InvestigationState, ToolRequest
from insightiq.tools.registry import ToolRegistry

ROOT_CAUSE_CHAIN = [
    "Deployment deploy-284 changed the customer-region transformation.",
    "Legacy region values mapped to NULL, raising the null rate from 0.4% to 63.1%.",
    "The regional revenue model filters out rows whose customer region is NULL.",
    "Affected transactions were excluded and reported revenue fell by 40%.",
]


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
            arguments={"metric": "revenue", "current_value": 72000, "expected_value": 120000},
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
        return AgentDecision(
            reasoning_summary=(
                "The causal chain has sufficient deterministic evidence for the gate."
            ),
            final_proposal=FinalProposal(
                conclusion=(
                    "A customer-region transformation regression caused valid transactions to be "
                    "excluded from reporting; the 40% decline is a reporting understatement, not a "
                    "corresponding demand collapse."
                ),
                root_cause_chain=ROOT_CAUSE_CHAIN,
                recommendation=(
                    "Roll back or correct deployment deploy-284, backfill customer_region, "
                    "rerun the revenue models, and add a null-rate deployment gate for "
                    "critical dimensions."
                ),
            ),
        )


class OpenAIDecisionProvider(DecisionProvider):
    """Responses API provider that lets one model select only allowlisted custom tools."""

    def __init__(self, model: str, client: OpenAI | None = None) -> None:
        self.model = model
        self.client = client or OpenAI()

    def decide(self, state: InvestigationState, registry: ToolRegistry) -> AgentDecision:
        finish_schema = FinalProposal.model_json_schema()
        finish_schema["additionalProperties"] = False
        finish_schema["required"] = list(finish_schema.get("properties", {}))
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
                "deterministic business impact."
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
