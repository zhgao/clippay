"""Tests for the embeddable player (GET /embed/{job_id}) and the
"Embed on your website" section on the product page.

The embed page is chromeless (no navigation links at all) and its buy
flow mirrors the demo player: real M1 /api/orders first, labelled mock
checkout only as fallback. No test here touches the network, Gemini,
or real PayPal credentials.
"""
import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from tests.fakes import FAKE_PRODUCTS, FakePayPal

TOTE_PRODUCT = {
    "name": "Organic Cotton Tote Bag",
    "description": "An organic cotton tote bag.",
    "price": "12.00",
    "timestamp_seconds": 0.0,
}


@pytest.fixture
def client_with_job():
    db = Database(":memory:")
    app = create_app(db=db, paypal=FakePayPal())
    db.create_job("job123", "pitch.mp4", "/tmp/pitch.mp4")
    db.update_job(
        "job123",
        status="ready",
        segments=[],
        products=[dict(p) for p in FAKE_PRODUCTS] + [dict(TOTE_PRODUCT)],
    )
    return TestClient(app)


@pytest.fixture
def client_with_pending_job():
    db = Database(":memory:")
    app = create_app(db=db, paypal=FakePayPal())
    db.create_job("job999", "pitch.mp4", "/tmp/pitch.mp4")
    return TestClient(app)


def test_embed_page_renders_products_and_buy_buttons(client_with_job):
    resp = client_with_job.get("/embed/job123")
    assert resp.status_code == 200
    html = resp.text
    assert "Handmade Mug" in html and "$20.00" in html
    assert "Walnut Cutting Board" in html and "$45.00" in html
    assert "Organic Cotton Tote Bag" in html and "$12.00" in html
    assert "Buy with PayPal" in html
    # Buy flow mirrors the demo player: real orders first, labelled
    # mock checkout only as fallback.
    assert "/api/orders" in html
    assert "/api/watch/demo/checkout" in html
    assert "mock checkout" in html
    assert "No real PayPal payment" in html


def test_embed_page_has_no_navigation_chrome(client_with_job):
    html = client_with_job.get("/embed/job123").text
    assert "/dashboard" not in html
    assert "<a " not in html
    assert "Seller dashboard" not in html


def test_embed_page_keeps_tote_price_footnote(client_with_job):
    html = client_with_job.get("/embed/job123").text
    assert "did not clearly state that price" in html
    assert "does not claim" in html


def test_embed_page_demo_mode_labelled_without_credentials(client_with_job):
    html = client_with_job.get("/embed/job123").text
    assert "Demo mode" in html


def test_embed_unknown_job_is_404(client_with_job):
    resp = client_with_job.get("/embed/nope")
    assert resp.status_code == 404


def test_embed_pending_job_is_not_ready(client_with_pending_job):
    resp = client_with_pending_job.get("/embed/job999")
    assert resp.status_code == 200
    assert "not ready yet" in resp.text


def test_product_page_has_embed_section(client_with_job):
    html = client_with_job.get("/p/job123").text
    assert "Embed on your website" in html
    assert "no detour to another site" in html
    assert 'id="embed-code"' in html
    assert "Copy embed code" in html
    # The iframe src is built from the live origin in JS, never a
    # hardcoded domain, so local / fly.dev / custom domains all work.
    assert "window.location.origin" in html
    assert "/embed/" in html
    assert "job123" in html
