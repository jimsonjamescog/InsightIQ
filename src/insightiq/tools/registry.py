from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from insightiq.models import ToolResult

ToolHandler = Callable[[BaseModel], ToolResult]


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler

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
        return definition.handler(validated)

    def openai_tools(self) -> list[dict[str, Any]]:
        tools = []
        for definition in self._tools.values():
            schema = definition.input_model.model_json_schema()
            schema["additionalProperties"] = False
            schema["required"] = list(schema.get("properties", {}))
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
