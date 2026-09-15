from __future__ import annotations

import json
import re
from pathlib import Path

from insightiq.agent.investigator import Investigator
from insightiq.agent.providers import DeterministicDecisionProvider
from insightiq.tools import build_mock_registry


def normalize(value: str) -> set[str]:
    stop_words = {"a", "an", "and", "the", "to", "of", "from", "was", "is", "by"}
    return {word for word in re.findall(r"[a-z0-9]+", value.lower()) if word not in stop_words}


def semantic_token_recall(actual: str, expected: str) -> float:
    expected_tokens = normalize(expected)
    return len(normalize(actual) & expected_tokens) / max(1, len(expected_tokens))


def evaluate(scenario_path: Path | None = None) -> dict:
    source_path = Path(__file__).resolve().parents[3] / "scenarios" / "ground_truth.json"
    cwd_path = Path.cwd() / "scenarios" / "ground_truth.json"
    default_path = source_path if source_path.exists() else cwd_path
    scenario = json.loads((scenario_path or default_path).read_text(encoding="utf-8"))
    investigator = Investigator(build_mock_registry(), DeterministicDecisionProvider())
    state, report = investigator.investigate(scenario["question"])

    actual_rejected = {item.hypothesis_id for item in report.rejected_hypotheses}
    expected_rejected = set(scenario["expected_rejected_hypotheses"])
    traceable = sum(
        1
        for evidence in report.supporting_evidence
        if evidence.tool_name and evidence.query_id and evidence.source and evidence.execution_id
    )
    unsupported = sum(
        1
        for evidence in report.supporting_evidence
        if not all([evidence.tool_name, evidence.query_id, evidence.source, evidence.execution_id])
    )
    return {
        "scenario_id": scenario["scenario_id"],
        "passed_evidence_gate": report.evidence_gate.passed,
        "root_cause_token_recall": round(
            semantic_token_recall(report.conclusions[0], scenario["expected_root_cause"]), 3
        ),
        "hypothesis_rejection_accuracy": round(
            len(actual_rejected & expected_rejected) / max(1, len(expected_rejected)), 3
        ),
        "evidence_traceability_rate": round(traceable / max(1, len(report.supporting_evidence)), 3),
        "unsupported_evidence_rate": round(
            unsupported / max(1, len(report.supporting_evidence)), 3
        ),
        "tool_calls": report.statistics.tool_calls,
        "duration_ms": report.statistics.duration_ms,
        "status": state.status.value,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
