from fastapi.testclient import TestClient

from app.demo_data import build_demo_request
from app.main import app
from app.services import ledger_service


def test_demo_evaluate_and_ledger_commit_revalidates_amount(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_service, "DB_PATH", tmp_path / "ledger.sqlite3")
    client = TestClient(app)

    demo = client.get("/api/v1/microsave/demo-data")
    assert demo.status_code == 200
    request = demo.json()
    evaluation = client.post("/api/v1/microsave/evaluate", json=request)
    assert evaluation.status_code == 200
    recommendation = evaluation.json()["recommended_reserve"]
    assert recommendation > 0

    too_large = client.post(
        "/api/v1/microsave/ledger/commit",
        json={"evaluation_request": request, "action": "APPROVED", "requested_amount": recommendation + 100},
    )
    assert too_large.status_code == 409

    approved = client.post(
        "/api/v1/microsave/ledger/commit",
        json={"evaluation_request": request, "action": "APPROVED", "requested_amount": recommendation},
    )
    assert approved.status_code == 200
    assert approved.json()["simulated"] is True
    assert approved.json()["executed_amount"] == recommendation

    ledger = client.get(f"/api/v1/microsave/ledger/{request['merchant_id']}")
    assert ledger.status_code == 200
    assert len(ledger.json()) == 1


def test_skip_does_not_move_money(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_service, "DB_PATH", tmp_path / "ledger.sqlite3")
    client = TestClient(app)
    request = build_demo_request().model_dump(mode="json")
    response = client.post(
        "/api/v1/microsave/ledger/commit",
        json={"evaluation_request": request, "action": "SKIPPED", "requested_amount": 0},
    )
    assert response.status_code == 200
    assert response.json()["executed_amount"] == 0
    assert response.json()["balance_after"] == response.json()["balance_before"]
