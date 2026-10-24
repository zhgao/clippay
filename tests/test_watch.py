"""Tests for the demo in-video shopping player (GET /watch/demo).

The page reuses the unchanged M1 /api/orders path first; the labelled
mock checkout (POST /api/watch/demo/checkout) is only the fallback when
no PayPal credentials are configured. No test here touches the network,
Gemini, or real PayPal credentials.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from app.watch import DEMO_PRODUCTS, watch_page
from tests.fakes import FakePayPal

DEMO_VIDEO = os.path.join(
    os.path.dirname(__file__), "..", "data", "samples", "demo_watch.mp4"
)


@pytest.fixture
def app_client():
    db = Database(":memory:")
    app = create_app(db=db, paypal=FakePayPal(), demo_video_path=DEMO_VIDEO)
    return TestClient(app), db


@pytest.fixture
def app_client_no_video():
    db = Database(":memory:")
    app = create_app(
        db=db, paypal=FakePayPal(), demo_video_path="/nonexistent/demo.mp4"
    )
    return TestClient(app), db


def test_watch_page_renders_all_three_demo_products(app_client):
    client, _ = app_client
    resp = client.get("/watch/demo")
    assert resp.status_code == 200
    html = resp.text
    # Exact verified 2026-10-24 extraction results, names and prices verbatim.
    assert "Handmade Ceramic Mug" in html and "$20.00" in html
    assert "Walnut Cutting Board" in html and "$45.00" in html
    assert "Organic Cotton Tote Bag" in html and "$12.00" in html
    # One video element, three buyable cards, all present at once.
    assert "<video" in html
    assert html.count('data-product=') == 3
    # Deliberately NOT timestamp-gated (unlike /p/{job_id}).
    assert "Mentioned at" not in html


def test_watch_page_is_honest_about_mock_and_tote_price(app_client):
    client, _ = app_client
    html = client.get("/watch/demo").text
    # Mock state is labelled on the page itself, never as a real payment.
    assert "Demo mode" in html
    assert "no real payment" in html
    assert "real payment" in html.lower()
    # The tote bag's $12.00 must never be presented as spoken in the video.
    assert "did not clearly state that price" in html
    assert "does not claim" in html


def test_watch_page_product_data_matches_verified_extraction():
    assert [p["name"] for p in DEMO_PRODUCTS] == [
        "Handmade Ceramic Mug",
        "Walnut Cutting Board",
        "Organic Cotton Tote Bag",
    ]
    assert [p["price"] for p in DEMO_PRODUCTS] == ["20.00", "45.00", "12.00"]
    assert "Sandbox" in watch_page("ClipPay", checkout_mode="sandbox")
    assert "Demo mode" in watch_page("ClipPay", checkout_mode="demo")


def test_watch_video_served_and_missing_is_404(app_client, app_client_no_video):
    client, _ = app_client
    resp = client.get("/watch/demo/video")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert len(resp.content) > 10_000
    client_missing, _ = app_client_no_video
    assert client_missing.get("/watch/demo/video").status_code == 404
    # The page still renders (with its animated slide fallback) even
    # when the video file is absent.
    assert client_missing.get("/watch/demo").status_code == 200


def test_click_checkout_uses_m1_orders_path_first(app_client):
    # Simulates the page JS's first step under a configured PayPal
    # client (here FakePayPal): the unchanged M1 endpoint returns an
    # approval URL and stores the order record.
    client, db = app_client
    resp = client.post(
        "/api/orders",
        json={
            "amount": "20.00",
            "currency": "USD",
            "description": "Handmade Ceramic Mug",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "token=ORDER-123" in body["approve_url"]
    assert db.get_order("ORDER-123")["description"] == "Handmade Ceramic Mug"


def test_mock_checkout_is_labelled_and_not_a_real_order(app_client):
    client, db = app_client
    resp = client.post(
        "/api/watch/demo/checkout",
        json={"amount": "12.00", "description": "Organic Cotton Tote Bag"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "mock"
    assert body["status"] == "DEMO_COMPLETED"
    assert body["order_id"].startswith("DEMO-")
    assert "no real paypal payment" in body["note"].lower()
    # Mock orders must not pollute the seller dashboard's real orders.
    assert db.list_orders() == []
