from __future__ import annotations

from insightiq.models import Evidence, EvidenceClassification, ToolResult, new_id

STATEMENT_BUILDERS = {
    "compare_periods": lambda r: (
        f"{r['metric']} changed {r['percent_change']}%: "
        f"{r['baseline_value']} to {r['current_value']} {r['unit']}."
    ),
    "segment_metric": lambda r: (
        f"{r['metric']} breakdown by {r['dimension']} shows: "
        + ", ".join(f"{s['segment']} {s['percent_change']}%" for s in r["segments"])
        + "."
    ),
    "check_data_quality": lambda r: (
        f"{r['field']} null rate changed from {r['baseline_null_rate']:.1%} "
        f"to {r['current_null_rate']:.1%}; anomaly={r['anomaly']}."
    ),
    "get_deployments": lambda r: (
        f"Found {len(r['deployments'])} deployments in the incident window."
    ),
    "get_pipeline_runs": lambda r: f"Found {len(r['runs'])} pipeline runs in the incident window.",
    "inspect_schema_changes": lambda r: (
        f"Found {len(r['changes'])} recorded change(s) to {r['object_name']}."
    ),
    "get_dependencies": lambda r: (
        f"{r['object_name']} depends on {', '.join(r['upstream'])}; "
        f"filter logic is {r['filter_logic']}."
    ),
    "calculate_business_impact": lambda r: (
        f"Reported {r['metric']} is understated by {r['understatement']} {r['unit']} "
        f"({r['understatement_percent']}%)."
    ),
}


class EvidenceStore:
    def __init__(self) -> None:
        self._executions: dict[str, ToolResult] = {}

    def record_execution(self, result: ToolResult) -> None:
        self._executions[result.execution_id] = result

    def from_tool_result(
        self,
        result: ToolResult,
        *,
        supports: list[str] | None = None,
        contradicts: list[str] | None = None,
        strength: float = 0.9,
    ) -> Evidence:
        self.record_execution(result)
        statement_builder = STATEMENT_BUILDERS.get(result.tool_name)
        statement = statement_builder(result.result) if statement_builder else str(result.result)
        return Evidence(
            evidence_id=new_id("evidence"),
            classification=EvidenceClassification.OBSERVED,
            observation_type=result.tool_name,
            statement=statement,
            tool_name=result.tool_name,
            execution_id=result.execution_id,
            query_id=result.query_id,
            source=result.source,
            timestamp=result.timestamp,
            supports=supports or [],
            contradicts=contradicts or [],
            strength=strength,
        )

    def validate(self, evidence: Evidence) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if evidence.classification == EvidenceClassification.OBSERVED:
            if not evidence.execution_id or evidence.execution_id not in self._executions:
                errors.append("Observed evidence has no recorded tool execution.")
            else:
                result = self._executions[evidence.execution_id]
                if evidence.tool_name != result.tool_name:
                    errors.append("Evidence tool name does not match its execution.")
                if evidence.query_id != result.query_id:
                    errors.append("Evidence query ID does not match its execution.")
                if evidence.source != result.source:
                    errors.append("Evidence source does not match its execution.")
        return not errors, errors

    def validate_all(self, evidence: list[Evidence]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        for item in evidence:
            valid, item_errors = self.validate(item)
            errors.extend(f"{item.evidence_id}: {error}" for error in item_errors)
        return not errors, errors
