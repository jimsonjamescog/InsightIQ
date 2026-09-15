import json
from types import SimpleNamespace

from insightiq.agent.providers import OpenAIDecisionProvider
from insightiq.models import InvestigationState
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


def test_openai_provider_accepts_structured_finish_call():
    call = SimpleNamespace(
        type="function_call",
        name="finish_investigation",
        arguments=json.dumps(
            {
                "conclusion": "Supported conclusion",
                "root_cause_chain": ["one", "two", "three", "four"],
                "recommendation": "Correct and backfill the transformation.",
            }
        ),
    )
    provider = OpenAIDecisionProvider("test-model", client=FakeClient([call]))
    state = InvestigationState(investigation_id="inv-test", question="Why did revenue fall?")

    decision = provider.decide(state, build_mock_registry())

    assert decision.final_proposal is not None
    assert decision.final_proposal.conclusion == "Supported conclusion"
