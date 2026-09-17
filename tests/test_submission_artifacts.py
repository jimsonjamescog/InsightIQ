import json
from pathlib import Path

from insightiq.models import InvestigationOutcome, InvestigationRequest

ROOT = Path(__file__).resolve().parents[1]


def test_required_submission_documents_exist():
    required = [
        "Problem.md",
        "README.md",
        "ARCHITECTURE.md",
        "docs/prompts.md",
        "docs/plan.md",
        "postman/InsightIQ.postman_collection.json",
        "sample-data/investigation_requests.json",
    ]

    assert all((ROOT / relative_path).is_file() for relative_path in required)


def test_sample_dataset_contains_twenty_valid_endpoint_records():
    records = json.loads((ROOT / "sample-data/investigation_requests.json").read_text())

    assert len(records) == 20
    assert len({record["record_id"] for record in records}) == 20
    for record in records:
        InvestigationRequest(question=record["question"])
        InvestigationOutcome(record["expected_outcome"])


def test_postman_collection_has_multiple_scenarios_and_automated_tests():
    path = ROOT / "postman/InsightIQ.postman_collection.json"
    collection = json.loads(path.read_text())

    def requests(items):
        for item in items:
            if "request" in item:
                yield item
            yield from requests(item.get("item", []))

    items = list(requests(collection["item"]))
    scripts = [
        line
        for item in items
        for event in item.get("event", [])
        for line in event["script"]["exec"]
        if "pm.test(" in line
    ]
    names = {item["name"] for item in items}

    assert collection["info"]["schema"].endswith("collection.json")
    assert len(items) >= 3
    assert len(scripts) >= 3
    assert {
        "Health check",
        "Create investigation",
        "Get investigation evidence",
        "Unknown investigation returns 404",
    } <= names
    assert any(
        "{{question}}" in item.get("request", {}).get("body", {}).get("raw", "")
        for item in items
    )
    readme = (ROOT / "README.md").read_text()
    assert "--iteration-data sample-data/investigation_requests.json" in readme


def test_architecture_contains_before_and_after_diagrams():
    architecture = (ROOT / "ARCHITECTURE.md").read_text()

    assert "Before: manual batch investigation" in architecture
    assert "After: evidence-grounded REST service" in architecture
    assert architecture.count("```mermaid") == 2
