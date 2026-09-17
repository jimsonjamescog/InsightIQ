import time

from fastapi.testclient import TestClient

from insightiq.api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_exposes_rejected_hypotheses():
    response = client.get("/")
    assert response.status_code == 200
    assert "Rejected hypotheses" in response.text
    assert "Current investigation" in response.text


def test_tool_registry_metadata_is_discoverable():
    response = client.get("/tools")
    assert response.status_code == 200
    tool = next(item for item in response.json()["tools"] if item["name"] == "compare_periods")
    assert tool["input_schema"]
    assert tool["output_schema"]
    assert tool["evidence_types"]
    assert tool["applicable_domains"]
    assert tool["capabilities"]
    assert tool["cost_or_latency_hint"]


def test_background_investigation_exposes_live_progress():
    started = client.post(
        "/investigations/start",
        json={"question": "Why did customer region data become incomplete?"},
    )
    assert started.status_code == 202
    investigation_id = started.json()["investigation_id"]

    for _ in range(100):
        state = client.get(f"/investigations/{investigation_id}").json()
        if state["status"] != "RUNNING":
            break
        time.sleep(0.05)

    assert state["events"]
    assert any(item["event_type"] == "EVIDENCE_SEEKING" for item in state["events"])
    assert state["status"] == "COMPLETED"
    assert client.get(f"/investigations/{investigation_id}/report").status_code == 200


def test_create_and_retrieve_investigation():
    created = client.post(
        "/investigations",
        json={"question": "Why did reported revenue decrease yesterday?"},
    )
    assert created.status_code == 200
    report = created.json()
    investigation_id = report["investigation_id"]
    assert report["evidence_gate"]["passed"] is True
    assert all(
        link["classification"] in {"OBSERVED", "INFERRED"} and link["evidence_ids"]
        for link in report["root_cause_chain"]
    )

    assert client.get(f"/investigations/{investigation_id}").status_code == 200
    assert client.get(f"/investigations/{investigation_id}/evidence").status_code == 200
    assert client.get(f"/investigations/{investigation_id}/graph").status_code == 200
    assert client.get(f"/investigations/{investigation_id}/report").json() == report


def test_unknown_investigation_is_404():
    response = client.get("/investigations/unknown")
    assert response.status_code == 404
