import json
from types import SimpleNamespace

import pytest

from insightiq.agent.providers import OpenAIDecisionProvider
from insightiq.api import main
from insightiq.config import Settings
from insightiq.models import HypothesisStatus, InvestigationState
from insightiq.tools import build_mock_registry


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(output=self.output, usage=None)


class FakeClient:
    def __init__(self, output):
        self.responses = FakeResponses(output)


def test_api_passes_configured_key_to_openai_provider(monkeypatch):
    captured = {}

    class Provider:
        def __init__(self, model, *, api_key):
            captured.update(model=model, api_key=api_key)

    monkeypatch.setattr(
        main,
        "settings",
        Settings(agent_mode="openai", openai_model="test-model", OPENAI_API_KEY="test-key"),
    )
    monkeypatch.setattr(main, "OpenAIDecisionProvider", Provider)

    main.build_provider()

    assert captured == {"model": "test-model", "api_key": "test-key"}


def test_api_requires_key_in_openai_mode(monkeypatch):
    monkeypatch.setattr(
        main,
        "settings",
        Settings(
            agent_mode="openai",
            openai_model="test-model",
            OPENAI_API_KEY=None,
            _env_file=None,
        ),
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        main.build_provider()


def test_openai_provider_accepts_allowlisted_function_call():
    call = SimpleNamespace(
        type="function_call",
        name="compare_periods",
        arguments=json.dumps(
            {
                "metric": "revenue",
                "current_period": "yesterday",
                "baseline_period": "previous_28_days",
            }
        ),
    )
    client = FakeClient([call])
    provider = OpenAIDecisionProvider("test-model", client=client)
    state = InvestigationState(investigation_id="inv-test", question="Why did revenue fall?")

    decision = provider.decide(state, build_mock_registry())

    assert decision.tool_request is not None
    assert decision.tool_request.name == "compare_periods"
    assert client.responses.kwargs["parallel_tool_calls"] is False
    assert client.responses.kwargs["store"] is False
    assert all(
        tool["parameters"]["additionalProperties"] is False
        for tool in client.responses.kwargs["tools"]
    )


def test_openai_provider_links_tool_call_to_hypothesis_requirement():
    call = SimpleNamespace(
        type="function_call",
        name="check_data_quality",
        arguments=json.dumps({"field": "customer_region", "period": "latest"}),
    )
    provider = OpenAIDecisionProvider("test-model", client=FakeClient([call]))
    registry = build_mock_registry()
    state = InvestigationState(investigation_id="inv-test", question="Why did revenue fall?")
    provider.initialize(state, registry)

    decision = provider.decide(state, registry)

    assert decision.investigation_intent is not None
    assert decision.investigation_intent.hypothesis_id == "H4"
    requirement = state.evidence_requirements["H4"][0]
    assert requirement.tool_name == "check_data_quality"


def test_openai_provider_expands_supported_follow_up():
    call = SimpleNamespace(
        type="function_call",
        name="get_deployments",
        arguments=json.dumps({"start": "incident_window", "end": "latest"}),
    )
    provider = OpenAIDecisionProvider("test-model", client=FakeClient([call]))
    registry = build_mock_registry()
    state = InvestigationState(investigation_id="inv-test", question="Why did revenue fall?")
    provider.initialize(state, registry)
    state.hypotheses[3].status = HypothesisStatus.SUPPORTED

    decision = provider.decide(state, registry)

    assert state.follow_up_questions == [
        "What caused the customer-region data-quality failure?"
    ]
    assert decision.investigation_intent is not None
    assert decision.investigation_intent.hypothesis_id == "H5"


def test_openai_provider_accepts_structured_finish_call():
    call = SimpleNamespace(
        type="function_call",
        name="finish_investigation",
        arguments=json.dumps(
            {
                "hypothesis_id": "H4",
                "conclusion": "Supported conclusion",
                "root_cause_chain": [
                    {
                        "link_id": f"cause-{index}",
                        "sequence": index,
                        "statement": statement,
                        "classification": "OBSERVED" if index < 4 else "INFERRED",
                        "evidence_ids": ["evidence-1"],
                    }
                    for index, statement in enumerate(["one", "two", "three", "four"], start=1)
                ],
                "recommendation": "Correct and backfill the transformation.",
            }
        ),
    )
    provider = OpenAIDecisionProvider("test-model", client=FakeClient([call]))
    state = InvestigationState(investigation_id="inv-test", question="Why did revenue fall?")

    decision = provider.decide(state, build_mock_registry())

    assert decision.final_proposal is not None
    assert decision.final_proposal.conclusion == "Supported conclusion"
    assert decision.final_proposal.root_cause_chain[3].classification == "INFERRED"
