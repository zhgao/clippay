"""API tests with a fake PayPal client and an in-memory SQLite DB."""
import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from app.paypal import PayPalClient, PayPalError
from tests.fakes import FakePayPal

ORDER_BODY = {
    "id": "ORDER-123",
    "status": "CREATED",
    "links": [
        {
            "rel": "approve",
            "href": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-123",
        }
    ],
}
CAPTURE_BODY = {
    "id": "ORDER-123",
    "status": "COMPLETED",
    "payer": {"email_address": "buyer@example.com"},
}


@pytest.fixture
def app_client():
    db = Database(":memory:")
    app = create_app(db=db, paypal=FakePayPal())
    return TestClient(app), db


def test_healthz(app_client):
    client, _ = app_client
    assert client.get("/healthz").json() == {"status": "ok", "service": "clippay"}


def test_create_order_stores_record(app_client):
    client, db = app_client
    resp = client.post(
        "/api/orders",
        json={"amount": "19.99", "currency": "USD", "description": "Clip video"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["order_id"] == "ORDER-123"
    assert body["approve_url"].endswith("token=ORDER-123")
    record = db.get_order("ORDER-123")
    assert record is not None
    assert record["amount"] == "19.99"
    assert record["status"] == "CREATED"


def test_get_order_and_404(app_client):
    client, db = app_client
    db.upsert_order("ORDER-123", "19.99")
    assert client.get("/api/orders/ORDER-123").status_code == 200
    assert client.get("/api/orders/NOPE").status_code == 404


def test_capture_order_updates_record(app_client):
    client, db = app_client
    db.upsert_order("ORDER-123", "19.99")
    resp = client.post("/api/orders/ORDER-123/capture")
    assert resp.status_code == 200
    record = db.get_order("ORDER-123")
    assert record["status"] == "COMPLETED"
    assert record["payer_email"] == "buyer@example.com"


def test_paypal_failure_becomes_502():
    db = Database(":memory:")
    app = create_app(
        db=db, paypal=FakePayPal(fail_with=PayPalError("boom"))
    )
    client = TestClient(app)
    resp = client.post("/api/orders", json={"amount": "1.00"})
    assert resp.status_code == 502
    assert "boom" in resp.json()["detail"]


def test_approval_url_none_when_missing():
    assert PayPalClient.approval_url({"id": "x", "links": []}) is None
