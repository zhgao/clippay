"""Tests for the overlay product rail and the PayPal JS SDK popup
checkout on the real player pages (/embed/{job_id} and /p/{job_id}).

The rail floats over the bottom of the video (above the control bar)
and its cards are always visible — never gated per second. In sandbox
mode the cards check out through a PayPal JS SDK popup that never
leaves the video page; the Secret never enters the page, and if the
SDK never loads the fallback Buy buttons keep the old flow. JS itself
cannot run inside pytest, so these tests assert on the rendered
markers (rail, SDK script URL, createOrder/onApprove wiring, fallback
buttons) plus the unchanged server endpoints underneath. No test here
touches the network, Gemini, or real PayPal credentials.
"""
import pytest
from fastapi.testclient import TestClient

from app import embed, pages
from app.db import Database
from app.main import create_app
from tests.fakes import FAKE_PRODUCTS, FakePayPal

TOTE_PRODUCT = {
    "name": "Organic Cotton Tote Bag",
    "description": "An organic cotton tote bag.",
    "price": "12.00",
    "timestamp_seconds": 0.0,
}


def _job_dict():
    return {
        "id": "job123",
        "filename": "pitch.mp4",
        "status": "ready",
        "products": [dict(p) for p in FAKE_PRODUCTS] + [dict(TOTE_PRODUCT)],
    }


@pytest.fixture
def demo_client():
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


def test_embed_overlay_rail_with_video_sandbox():
    html = embed.embed_page(
        _job_dict(), "ClipPay", checkout_mode="sandbox",
        has_video=True, paypal_client_id="TEST-CLIENT-ID",
    )
    # Rail over the video, all products inside it, always visible.
    assert "<div class=\"overlay-rail\">" in html
    assert "<div class=\"card overlay-card\">" in html
    assert "Handmade Mug" in html and "Walnut Cutting Board" in html
    assert "Organic Cotton Tote Bag" in html
    # SDK popup wiring: client id is the public identifier, and the
    # flow reuses the existing server endpoints (no new API).
    assert "sdk/js?client-id=TEST-CLIENT-ID" in html
    assert "createOrder" in html and "/api/orders" in html
    assert "onApprove" in html and "/capture" in html
    # Fallback stays in the markup until the SDK actually renders.
    assert "Buy with PayPal" in html
    # Honesty labels unchanged.
    assert "did not clearly state that price" in html


def test_embed_overlay_absent_without_video_but_sdk_still_offered():
    html = embed.embed_page(
        _job_dict(), "ClipPay", checkout_mode="sandbox",
        has_video=False, paypal_client_id="TEST-CLIENT-ID",
    )
    assert "<div class=\"overlay-rail\">" not in html
    assert "sdk/js?client-id=TEST-CLIENT-ID" in html
    assert "Buy with PayPal" in html


def test_embed_sandbox_without_client_id_has_no_sdk():
    html = embed.embed_page(
        _job_dict(), "ClipPay", checkout_mode="sandbox",
        has_video=True, paypal_client_id="",
    )
    assert "<div class=\"overlay-rail\">" in html
    assert "sdk/js" not in html


def test_embed_demo_mode_has_no_sdk_via_client(demo_client):
    html = demo_client.get("/embed/job123").text
    assert "sdk/js" not in html
    assert "Buy with PayPal" in html
    # Old redirect-or-mock flow untouched in demo mode.
    assert "/api/orders" in html
    assert "/api/watch/demo/checkout" in html


def test_product_overlay_and_sdk():
    html = pages.product_page(
        _job_dict(), "ClipPay", has_video=True,
        paypal_client_id="TEST-CLIENT-ID",
    )
    assert "<div class=\"overlay-rail\">" in html
    assert "<div class=\"card overlay-card\">" in html
    assert "sdk/js?client-id=TEST-CLIENT-ID" in html
    assert "createOrder" in html and "onApprove" in html
    assert "Buy with PayPal" in html


def test_product_overlay_without_sdk_still_overlays():
    html = pages.product_page(_job_dict(), "ClipPay", has_video=True)
    assert "<div class=\"overlay-rail\">" in html
    assert "sdk/js" not in html
    assert "Buy with PayPal" in html


def test_overlay_clears_controls_and_clicks_pass_through():
    html = embed.embed_page(
        _job_dict(), "ClipPay", checkout_mode="sandbox",
        has_video=True, paypal_client_id="TEST-CLIENT-ID",
    )
    # Raised from 44px in the second visual polish so no button edge
    # is ever pressed or clipped by the progress bar.
    assert "bottom: 64px" in html
    assert "pointer-events: none" in html
    assert "pointer-events: auto" in html


def test_overlay_pending_job_has_no_rail():
    job = _job_dict()
    job["status"] = "transcribing"
    html = embed.embed_page(
        job, "ClipPay", checkout_mode="sandbox",
        has_video=True, paypal_client_id="TEST-CLIENT-ID",
    )
    assert "<div class=\"overlay-rail\">" not in html
    assert "not ready yet" in html


def test_overlay_no_products_means_no_rail_but_video_stays():
    job = _job_dict()
    job["products"] = []
    html = embed.embed_page(
        job, "ClipPay", checkout_mode="sandbox",
        has_video=True, paypal_client_id="TEST-CLIENT-ID",
    )
    assert "<div class=\"overlay-rail\">" not in html
    assert "<video" in html
    assert "No purchasable products" in html
