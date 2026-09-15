from fastapi.testclient import TestClient

from insightiq.api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_retrieve_investigation():
    created = client.post(
        "/investigations",
        json={"question": "Why did reported revenue decrease yesterday?"},
    )
    assert created.status_code == 200
    report = created.json()
    investigation_id = report["investigation_id"]
    assert report["evidence_gate"]["passed"] is True

    assert client.get(f"/investigations/{investigation_id}").status_code == 200
    assert client.get(f"/investigations/{investigation_id}/evidence").status_code == 200
    assert client.get(f"/investigations/{investigation_id}/graph").status_code == 200
    assert client.get(f"/investigations/{investigation_id}/report").json() == report


def test_unknown_investigation_is_404():
    response = client.get("/investigations/unknown")
    assert response.status_code == 404
