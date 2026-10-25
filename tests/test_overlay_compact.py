"""Tests for the compact overlay rail and the cancel/blocked/failure
error classification on the real player pages.

George's screenshot of the embed page showed three defects: overlay
cards so tall they covered the video (long description + timestamp +
three PayPal funding buttons each), the last card cut off at the right
edge, and a red "Checkout failed: Window is closed" after the buyer
simply closed the popup. These tests pin the fixes:

- overlay cards carry name + price + one PayPal button only;
- the rail is height-capped, clears the control bar, and scrolls
  horizontally with snap points so the last card slides fully in;
- the SDK renders PayPal funding only (paylater/card disabled);
- a closed popup maps to a neutral cancel note, a blocked popup to
  a neutral hint, and only real failures stay red.

JS itself cannot run inside pytest, so the page tests assert on the
rendered markers, while the error classifier itself is unit-tested in
Python — the page JS embeds the very same keyword lists.
"""
import pytest

from app import embed, pages
from app.checkout_errors import (
    BLOCKED_MESSAGE,
    CANCEL_MESSAGE,
    classify_checkout_error,
)

TOTE_PRODUCT = {
    "name": "Organic Cotton Tote Bag",
    "description": "An organic cotton tote bag.",
    "price": "12.00",
    "timestamp_seconds": 0.0,
}

PRODUCTS = [
    {
        "name": "Handmade Mug",
        "description": "A handmade ceramic mug.",
        "price": "20.00",
        "timestamp_seconds": 12.5,
    },
    {
        "name": "Walnut Cutting Board",
        "description": "A walnut cutting board.",
        "price": "45.00",
        "timestamp_seconds": 40.0,
    },
    dict(TOTE_PRODUCT),
]


def _job_dict():
    return {
        "id": "job123",
        "filename": "pitch.mp4",
        "status": "ready",
        "products": [dict(p) for p in PRODUCTS],
    }


def _embed_html():
    return embed.embed_page(
        _job_dict(), "ClipPay", checkout_mode="sandbox",
        has_video=True, paypal_client_id="TEST-CLIENT-ID",
    )


def _product_html():
    return pages.product_page(
        _job_dict(), "ClipPay", has_video=True,
        paypal_client_id="TEST-CLIENT-ID",
    )


def _rail_segment(html):
    """The overlay rail's markup only (everything up to the next
    section after the rail)."""
    after = html.split('<div class="overlay-rail">', 1)[1]
    cuts = [
        after.index(marker)
        for marker in ('<div id="confirm"', '<div class="card">', "<h2>Embed")
        if marker in after
    ]
    if cuts:
        after = after[: min(cuts)]
    return after


# -- error classification (the testable function) -----------------------

@pytest.mark.parametrize("message", [
    "Window is closed, can not determine type",
    "WINDOW IS CLOSED",
    "Popup closed without completing payment",
    "User closed the popup window",
    "user cancelled",
    "Payment canceled by buyer",
])
def test_classifier_cancel(message):
    assert classify_checkout_error(message) == "cancel"


@pytest.mark.parametrize("message", [
    "Popup blocked by the browser",
    "pop-up blocked",
    "Failed to open popup",
    "Popup failed to open",
])
def test_classifier_blocked(message):
    assert classify_checkout_error(message) == "blocked"


@pytest.mark.parametrize("message", [
    "order failed",
    "Network error",
    "capture failed",
    "",
    None,
    500,
])
def test_classifier_real_failure(message):
    assert classify_checkout_error(message) == "failure"


def test_classifier_cancel_checked_before_blocked():
    # A message matching both lists is a cancel, never a blocked hint.
    assert classify_checkout_error("popup closed, cancel") == "cancel"


# -- compact overlay cards ----------------------------------------------

def test_embed_overlay_cards_are_compact():
    rail = _rail_segment(_embed_html())
    assert rail.count('<div class="card overlay-card">') == 3
    # Name + price + one PayPal button container per card — and
    # nothing else: no long description, no timestamp line.
    assert "Mentioned at" not in rail
    assert "A handmade ceramic mug." not in rail
    assert "A walnut cutting board." not in rail
    assert "An organic cotton tote bag." not in rail
    assert rail.count('class="pp-buttons"') == 3
    assert rail.count("fallback-buy") == 3
    assert "$20.00" in rail and "$45.00" in rail and "$12.00" in rail


def test_embed_overlay_no_paylater_or_card_buttons():
    html = _embed_html()
    # The SDK is told to disable both, and Buttons is pinned to the
    # PayPal funding source — so no Pay Later / card button can render.
    assert "disable-funding=paylater,card" in html
    assert "fundingSource: paypal.FUNDING.PAYPAL" in html
    assert "Pay Later" not in html
    assert "借记卡" not in html


def test_rail_height_capped_and_scrolls_with_snap():
    html = _embed_html()
    assert "max-height: 132px" in html
    assert "overflow-x: auto" in html
    assert "scroll-snap-type: x mandatory" in html
    assert "scroll-snap-align: start" in html
    assert "scroll-padding-right:" in html
    assert "flex: 0 0 180px" in html
    # Control bar still cleared, clicks still pass through to video.
    assert "bottom: 44px" in html
    assert "pointer-events: none" in html
    assert "pointer-events: auto" in html


# -- cancel / blocked / failure messaging --------------------------------

def test_rendered_pages_map_cancel_and_blocked_to_neutral_notes():
    for html in (_embed_html(), _product_html()):
        # The classifier and both neutral messages are in the page JS.
        assert "classifyCheckoutError" in html
        assert "window is closed" in html
        # Neutral notes go through textContent, never the red .err span.
        assert f'msg.textContent = "{CANCEL_MESSAGE}"' in html
        assert f'msg.textContent = "{BLOCKED_MESSAGE}"' in html
        # The red failure template survives for real failures only.
        assert '<span class="err">Checkout failed: ' in html


def test_cancel_message_is_not_wrapped_in_red():
    html = _embed_html()
    assert f'<span class="err">{CANCEL_MESSAGE}' not in html
    assert f'<span class="err">{BLOCKED_MESSAGE}' not in html


# -- full info preserved on the product page, not the embed -------------

def test_product_page_keeps_full_info_below_video():
    html = _product_html()
    rail = _rail_segment(html)
    # Overlay cards stay compact…
    assert "Mentioned at" not in rail
    assert "A handmade ceramic mug." not in rail
    # …while the full cards below the video keep description + time.
    assert "Mentioned at" in html
    assert "A handmade ceramic mug." in html
    assert "A walnut cutting board." in html


def test_embed_page_stays_chromeless_without_below_cards():
    html = _embed_html()
    assert "A handmade ceramic mug." not in html
    assert "Mentioned at" not in html
    # Tote honesty footnote still present.
    assert "did not clearly state that price" in html
