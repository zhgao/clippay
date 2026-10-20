"""Webhook receiver tests: signature verification + event handling."""
import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from tests.fakes import FakePayPal

HEADERS = {
    "paypal-transmission-id": "t1",
    "paypal-transmission-time": "2026-01-01T00:00:00Z",
    "paypal-cert-url": "https://example.com/cert",
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-transmission-sig": "sig",
}


def make_client(verify_result=True):
    db = Database(":memory:")
    db.upsert_order("ORDER-123", "19.99")
    app = create_app(db=db, paypal=FakePayPal(verify_result=verify_result))
    return TestClient(app), db


def test_approved_event_marks_order_approved():
    client, db = make_client()
    event = {"event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "ORDER-123"}}
    resp = client.post("/api/webhooks/paypal", json=event, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "CHECKOUT.ORDER.APPROVED"
    assert db.get_order("ORDER-123")["status"] == "APPROVED"


def test_capture_completed_event_marks_order_completed():
    client, db = make_client()
    event = {
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "supplementary_data": {"related_ids": {"order_id": "ORDER-123"}},
            "payer": {"email_address": "buyer@example.com"},
        },
    }
    resp = client.post("/api/webhooks/paypal", json=event, headers=HEADERS)
    assert resp.status_code == 200
    record = db.get_order("ORDER-123")
    assert record["status"] == "COMPLETED"
    assert record["payer_email"] == "buyer@example.com"


def test_unknown_event_is_acknowledged_but_ignored():
    client, db = make_client()
    event = {"event_type": "SOMETHING.ELSE", "resource": {}}
    resp = client.post("/api/webhooks/paypal", json=event, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["received"] is True
    assert db.get_order("ORDER-123")["status"] == "CREATED"


def test_invalid_signature_is_rejected():
    client, db = make_client(verify_result=False)
    event = {"event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "ORDER-123"}}
    resp = client.post("/api/webhooks/paypal", json=event, headers=HEADERS)
    assert resp.status_code == 400
    assert db.get_order("ORDER-123")["status"] == "CREATED"
