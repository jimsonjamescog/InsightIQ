from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI

from insightiq.agent.context import generate_hypotheses, understand_question
from insightiq.models import (
    AgentDecision,
    EvidenceClassification,
    FinalProposal,
    HypothesisStatus,
    InvestigationEvent,
    InvestigationIntent,
    InvestigationPriority,
    InvestigationState,
    RootCauseLink,
    ToolRequest,
)
from insightiq.tools.registry import ToolRegistry, strict_json_schema


class DecisionProvider(ABC):
    def initialize(self, state: InvestigationState, registry: ToolRegistry) -> None:
        hypotheses, requirements, _ = generate_hypotheses(state.question)
        state.hypotheses.extend(hypotheses)
        state.evidence_requirements.update(requirements)

    @abstractmethod
    def decide(self, state: InvestigationState, registry: ToolRegistry) -> AgentDecision:
        raise NotImplementedError


class DeterministicDecisionProvider(DecisionProvider):
    """Question-driven offline planner using context and registered capabilities."""

    def decide(self, state: InvestigationState, registry: ToolRegistry) -> AgentDecision:
        _expand_supported_follow_ups(state, registry)
        selection = self._select_next_requirement(state, registry)
        if selection:
            hypothesis, requirement, tool_name = selection
            question = hypothesis.question if hypothesis else state.question
            intent = InvestigationIntent(
                question=question,
                hypothesis_id=hypothesis.hypothesis_id if hypothesis else None,
                hypothesis=hypothesis.description if hypothesis else None,
                evidence_sought=requirement.description,
                selected_tool=tool_name,
                reason=(
                    "Selected from the Tool Registry because its capabilities match the "
                    "highest-value unresolved evidence gap."
                ),
            )
            requirement.tool_name = tool_name
            return AgentDecision(
                reasoning_summary=intent.reason,
                investigation_intent=intent,
                tool_request=ToolRequest(name=tool_name, arguments=requirement.arguments),
            )

        proposal = self._synthesize(state)
        return AgentDecision(
            reasoning_summary=(
                "The evidence supports a traceable causal chain."
                if proposal
                else "Available registered tools cannot resolve the remaining evidence gaps."
            ),
            final_proposal=proposal,
        )

    @staticmethod
    def _select_next_requirement(state: InvestigationState, registry: ToolRegistry):
        context = understand_question(state.question)
        candidates = []
        priority_value = {
            InvestigationPriority.HIGH: 3,
            InvestigationPriority.MEDIUM: 2,
            InvestigationPriority.LOW: 1,
        }
        for owner_id, requirements in state.evidence_requirements.items():
            hypothesis = next(
                (item for item in state.hypotheses if item.hypothesis_id == owner_id), None
            )
            if hypothesis and hypothesis.status in {
                HypothesisStatus.REJECTED,
                HypothesisStatus.INSUFFICIENT_EVIDENCE,
            }:
                continue
            for requirement in requirements:
                if requirement.satisfied or requirement.unavailable:
                    continue
                definition = registry.discover(requirement.capability, context.domains)
                if not definition:
                    requirement.unavailable = True
                    continue
                priority = priority_value.get(
                    hypothesis.investigation_priority if hypothesis else InvestigationPriority.HIGH,
                    1,
                )
                if hypothesis is None:
                    priority += 2
                cost = {"LOW": 0.1, "MEDIUM": 0.4, "HIGH": 0.8}.get(
                    definition.cost_or_latency_hint,
                    0.5,
                )
                candidates.append(
                    (
                        priority + requirement.information_value - cost,
                        hypothesis,
                        requirement,
                        definition.name,
                    )
                )
        if not candidates:
            return None
        _, hypothesis, requirement, tool_name = max(candidates, key=lambda item: item[0])
        return hypothesis, requirement, tool_name

    @staticmethod
    def _synthesize(state: InvestigationState) -> FinalProposal | None:
        supported = [item for item in state.hypotheses if item.status == HypothesisStatus.SUPPORTED]
        if not supported:
            return None
        leaves = [
            item
            for item in supported
            if not any(child.parent_hypothesis_id == item.hypothesis_id for child in supported)
            and not (
                item.follow_up_question and item.follow_up_question in state.follow_up_questions
            )
        ]
        if not leaves:
            return None

        def depth(item):
            value = 0
            parent_id = item.parent_hypothesis_id
            while parent_id:
                value += 1
                parent = next(
                    entry for entry in state.hypotheses if entry.hypothesis_id == parent_id
                )
                parent_id = parent.parent_hypothesis_id
            return value

        target = max(leaves, key=lambda item: (depth(item), item.support_score))
        ancestor_ids = {target.hypothesis_id}
        parent_id = target.parent_hypothesis_id
        while parent_id:
            ancestor_ids.add(parent_id)
            parent = next(item for item in state.hypotheses if item.hypothesis_id == parent_id)
            parent_id = parent.parent_hypothesis_id

        causal_evidence = [
            item
            for item in state.evidence
            if ancestor_ids.intersection(item.supports)
            or item.evidence_type.value == "BUSINESS_IMPACT"
        ]
        if len(causal_evidence) < 3:
            return None
        order = {
            "TEMPORAL": 0,
            "STATISTICAL": 1,
            "DEPENDENCY": 2,
            "HISTORICAL": 3,
            "BUSINESS_IMPACT": 4,
        }
        causal_evidence.sort(key=lambda item: order.get(item.evidence_type.value, 9))
        links = [
            RootCauseLink(
                link_id=f"cause-{index}",
                sequence=index,
                statement=evidence.statement,
                classification=EvidenceClassification.OBSERVED,
                evidence_ids=[evidence.evidence_id],
            )
            for index, evidence in enumerate(causal_evidence, start=1)
        ]
        links.append(
            RootCauseLink(
                link_id=f"cause-{len(links) + 1}",
                sequence=len(links) + 1,
                statement=(
                    f"The collected evidence supports {target.description.rstrip('.').casefold()}."
                ),
                classification=EvidenceClassification.INFERRED,
                evidence_ids=[item.evidence_id for item in causal_evidence],
            )
        )
        return FinalProposal(
            hypothesis_id=target.hypothesis_id,
            conclusion=(
                f"Evidence establishes that {target.description.rstrip('.').casefold()}. "
                "Supporting chain: " + " ".join(item.statement for item in causal_evidence)
            ),
            root_cause_chain=links,
            recommendation=(
                "Correct the supported failure, backfill affected data, rerun dependent models, "
                "and add a preventive quality gate."
            ),
        )


class OpenAIDecisionProvider(DecisionProvider):
    """Responses API planner constrained to discovered, allowlisted tools."""

    def __init__(
        self,
        model: str,
        client: OpenAI | None = None,
        *,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.client = client or OpenAI(api_key=api_key)

    def decide(self, state: InvestigationState, registry: ToolRegistry) -> AgentDecision:
        _expand_supported_follow_ups(state, registry)
        finish_tool = {
            "type": "function",
            "name": "finish_investigation",
            "description": "Propose a conclusion only after a complete causal chain exists.",
            "parameters": strict_json_schema(FinalProposal),
            "strict": True,
        }
        unresolved_tools = _unresolved_tools(state, registry)
        model_tools = [
            tool for tool in registry.openai_tools() if tool["name"] in unresolved_tools
        ]
        if not model_tools:
            model_tools = [finish_tool]
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "You are InsightIQ, a cautious, generic business investigator. Investigate the "
                "highest-priority unresolved evidence gap and select exactly one discovered tool. "
                "Never invent facts, calculations, IDs, or sources. Do not assume a revenue path. "
                "Use finish_investigation only for a traceable causal chain."
            ),
            input=json.dumps(_state_for_model(state, registry), default=str),
            tools=model_tools,
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
            model_proposal = FinalProposal.model_validate(arguments)
            proposal = DeterministicDecisionProvider._synthesize(state)
            if proposal:
                proposal.recommendation = model_proposal.recommendation
            else:
                proposal = model_proposal
            return AgentDecision(
                reasoning_summary="The model proposed a final evidence-grounded conclusion.",
                final_proposal=proposal,
            )
        if call.name not in registry.names:
            raise RuntimeError(f"The model selected a non-allowlisted tool: {call.name}")
        hypothesis, requirement = _requirement_for_tool(state, registry, call.name)
        if requirement:
            requirement.tool_name = call.name
        return AgentDecision(
            reasoning_summary=f"The model selected {call.name} for an unresolved evidence gap.",
            investigation_intent=InvestigationIntent(
                question=hypothesis.question if hypothesis else state.question,
                hypothesis_id=hypothesis.hypothesis_id if hypothesis else None,
                hypothesis=hypothesis.description if hypothesis else None,
                evidence_sought=(
                    requirement.description
                    if requirement
                    else "Evidence selected by the model from current unresolved gaps."
                ),
                selected_tool=call.name,
                reason="The registered capability matches the model's current investigation plan.",
            ),
            tool_request=ToolRequest(name=call.name, arguments=arguments),
        )


def _expand_supported_follow_ups(state: InvestigationState, registry: ToolRegistry) -> None:
    for hypothesis in list(state.hypotheses):
        question = hypothesis.follow_up_question
        if hypothesis.status != HypothesisStatus.SUPPORTED or not question:
            continue
        if question in state.follow_up_questions:
            continue
        state.follow_up_questions.append(question)
        generated, requirements, _ = generate_hypotheses(
            question,
            start_number=len(state.hypotheses) + 1,
            parent_id=hypothesis.hypothesis_id,
        )
        completed_tools = {result.tool_name for result in state.tool_results}
        for items in requirements.values():
            for requirement in items:
                definition = _definition_for_requirement(requirement, registry)
                if definition in completed_tools:
                    requirement.satisfied = True
                    requirement.tool_name = definition
        state.hypotheses.extend(generated)
        state.evidence_requirements.update(requirements)
        state.events.append(
            _event(
                state,
                "FOLLOW_UP_CREATED",
                f"Created recursive investigation: {question}",
                hypothesis_id=hypothesis.hypothesis_id,
            )
        )


def _definition_for_requirement(requirement, registry: ToolRegistry) -> str | None:
    definition = registry.discover(requirement.capability)
    return definition.name if definition else None


def _unresolved_tools(state: InvestigationState, registry: ToolRegistry) -> set[str]:
    names = set()
    for owner_id, requirements in state.evidence_requirements.items():
        hypothesis = next(
            (item for item in state.hypotheses if item.hypothesis_id == owner_id), None
        )
        if hypothesis and hypothesis.status in {
            HypothesisStatus.REJECTED,
            HypothesisStatus.INSUFFICIENT_EVIDENCE,
        }:
            continue
        for requirement in requirements:
            if not requirement.satisfied and not requirement.unavailable:
                name = _definition_for_requirement(requirement, registry)
                if name:
                    names.add(name)
    return names


def _requirement_for_tool(
    state: InvestigationState,
    registry: ToolRegistry,
    tool_name: str,
):
    context = understand_question(state.question)
    candidates = []
    for owner_id, requirements in state.evidence_requirements.items():
        hypothesis = next(
            (item for item in state.hypotheses if item.hypothesis_id == owner_id), None
        )
        for requirement in requirements:
            if requirement.satisfied or requirement.unavailable:
                continue
            definition = registry.discover(requirement.capability, context.domains)
            if definition and definition.name == tool_name:
                candidates.append((hypothesis, requirement))
    return candidates[0] if candidates else (None, None)


def _event(
    state: InvestigationState,
    event_type: str,
    message: str,
    **kwargs: Any,
) -> InvestigationEvent:
    return InvestigationEvent(
        sequence=len(state.events) + 1,
        event_type=event_type,
        message=message,
        **kwargs,
    )


def _state_for_model(state: InvestigationState, registry: ToolRegistry) -> dict[str, Any]:
    return {
        "question": state.question,
        "steps_taken": state.steps_taken,
        "hypotheses": [item.model_dump(mode="json") for item in state.hypotheses],
        "evidence_requirements": {
            key: [item.model_dump(mode="json") for item in value]
            for key, value in state.evidence_requirements.items()
        },
        "evidence": [item.model_dump(mode="json") for item in state.evidence],
        "business_impact": state.business_impact,
        "tool_registry": registry.describe(),
    }
