from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from insightiq.models import EvidenceFinding, EvidenceType, ToolResult

ToolHandler = Callable[[BaseModel], ToolResult]
ResultInterpreter = Callable[[ToolResult], list[EvidenceFinding]]


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()

    def normalize(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler
    output_schema: dict[str, Any] = Field(default_factory=dict)
    evidence_types: list[EvidenceType] = Field(default_factory=list)
    applicable_domains: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    cost_or_latency_hint: str = "LOW"
    interpreter: ResultInterpreter | None = None

    model_config = {"arbitrary_types_allowed": True}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self._tools:
            raise ValueError(f"Tool is not allowlisted: {name}")
        definition = self._tools[name]
        validated = definition.input_model.model_validate(arguments)
        result = definition.handler(validated)
        result.arguments = validated.model_dump(mode="json")
        return result

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "description": item.description,
                "input_schema": item.input_model.model_json_schema(),
                "output_schema": item.output_schema,
                "evidence_types": [kind.value for kind in item.evidence_types],
                "applicable_domains": item.applicable_domains,
                "capabilities": item.capabilities,
                "cost_or_latency_hint": item.cost_or_latency_hint,
            }
            for item in self._tools.values()
        ]

    def discover(self, capability: str, domains: list[str] | None = None) -> ToolDefinition | None:
        domains = domains or []
        candidates = [item for item in self._tools.values() if capability in item.capabilities]
        if domains:
            matching = [
                item
                for item in candidates
                if not item.applicable_domains
                or "all" in item.applicable_domains
                or set(domains) & set(item.applicable_domains)
            ]
            candidates = matching or candidates
        cost_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        return min(
            candidates, key=lambda item: cost_rank.get(item.cost_or_latency_hint, 9), default=None
        )

    def interpret(self, result: ToolResult) -> list[EvidenceFinding]:
        definition = self._tools[result.tool_name]
        return definition.interpreter(result) if definition.interpreter else []

    def openai_tools(self) -> list[dict[str, Any]]:
        tools = []
        for definition in self._tools.values():
            schema = strict_json_schema(definition.input_model)
            tools.append(
                {
                    "type": "function",
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": schema,
                    "strict": True,
                }
            )
        return tools
