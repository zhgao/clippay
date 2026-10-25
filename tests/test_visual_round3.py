"""Third visual small-fix round for the embed and product players.

A real browser re-read of the second polish found it genuinely
better and close to premium, but flagged three remaining visual
defects, all pinned here on both pages:

1. the silver pill hangs half out of the card: the button straddles
   the card's bottom edge, half on the card and half on the black
   video, so card + button do not read as one component. The card
   now carries bottom padding plus overflow: hidden, and the rail
   cap is raised to fit the taller content, so the pill always lands
   fully inside the card;
2. the product name is not prominent inside the card: at desktop
   size only the price and the pill read clearly, and the name
   blends into them. The name is now bigger and bolder with its
   own line budget (two-line clamp) and clear spacing from the
   price below it — no long description is added back;
3. the cancel note is in Chinese while the rest of the embed UI is
   English. It is now English (and so is the blocked-popup hint,
   the same language-mismatch class); the neutral small muted
   styling is unchanged.

What is NOT claimed here: the blue focus ring inside PayPal's
cross-origin iframe is not styleable from the page and is out of
scope for this round.
"""
import re

import pytest

from app import embed, pages
from app.checkout_errors import BLOCKED_MESSAGE, CANCEL_MESSAGE

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
    {
        "name": "Organic Cotton Tote Bag",
        "description": "An organic cotton tote bag.",
        "price": "12.00",
        "timestamp_seconds": 0.0,
    },
]


def _job_dict():
    return {
        "id": "job123",
        "filename": "pitch.mp4",
        "status": "ready",
        "products": [dict(p) for p in PRODUCTS],
    }


def _embed_html(sdk=True):
    return embed.embed_page(
        _job_dict(), "ClipPay",
        checkout_mode="sandbox" if sdk else "demo",
        has_video=True,
        paypal_client_id="TEST-CLIENT-ID" if sdk else "",
    )


def _product_html(sdk=True):
    return pages.product_page(
        _job_dict(), "ClipPay", has_video=True,
        paypal_client_id="TEST-CLIENT-ID" if sdk else "",
    )


def _rule(css, selector):
    m = re.search(re.escape(selector) + r" \{([^}]*)\}", css)
    assert m, f"missing CSS rule: {selector}"
    return m.group(1)


# -- 1. pill fully inside the card ---------------------------------------

@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_card_has_bottom_padding_and_clips_overflow(css):
    card = _rule(css, ".overlay-card")
    # Bottom breathing room so the pill never touches the card edge,
    # and overflow hidden so no button edge can ever escape the
    # rounded card onto the video.
    assert "padding: .8rem .9rem 1rem" in card
    assert "overflow: hidden" in card
    # The SDK iframe is a block, so no inline baseline gap eats the
    # bottom padding from inside.
    assert ".overlay-card .pp-buttons iframe { display: block; }" in css


@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_rail_cap_removed_name_no_longer_clipped(css):
    # Round-4 correction of this test's old claim: the 168px cap did
    # NOT fit taller cards — it left a 144px content box while a
    # rendered card needs ~156-171px, and the whole deficit came out
    # of the product name (the only shrinkable element: overflow
    # hidden gives it an automatic minimum of 0), so the name vanished
    # the moment the pill rendered. The rail must therefore carry no
    # max-height at all: it sizes to content, and the cards grow
    # upward from the 64px control clearance.
    rail = _rule(css, ".overlay-rail")
    assert "max-height" not in rail
    assert "max-height: 132px" not in rail
    assert "bottom: 64px" in rail


# -- 2. product name hierarchy -------------------------------------------

@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_name_bigger_bolder_with_own_line_budget(css):
    h3 = _rule(css, ".overlay-card h3")
    assert "font-size: 1.05rem" in h3
    assert "font-weight: 700" in h3
    # Two-line clamp: long names (e.g. Organic Cotton Tote Bag) wrap
    # instead of truncating to an ellipsis on one line, so a shopper
    # can tell at a glance which price belongs to which product.
    assert "-webkit-line-clamp: 2" in h3
    assert "white-space: normal" in h3
    price = _rule(css, ".overlay-card .price")
    # Clear vertical separation: name above, price below, then the
    # button — not one undifferentiated block.
    assert "margin: .2rem 0 .6rem" in price


# -- 3. cancel note in English --------------------------------------------

def test_cancel_and_blocked_notes_are_english():
    assert CANCEL_MESSAGE == "Cancelled — tap buy to try again"
    assert BLOCKED_MESSAGE == "Please allow popups for this site and try again"


@pytest.mark.parametrize("html_fn", [_embed_html, _product_html])
def test_rendered_pages_show_english_cancel_note(html_fn):
    html = html_fn(sdk=True)
    assert "Cancelled — tap buy to try again" in html
    assert "Please allow popups for this site and try again" in html
    assert "已取消" not in html
    assert "请允许" not in html


# -- supporting: no redundant tagline eating card height -----------------

@pytest.mark.parametrize("html_fn", [_embed_html, _product_html])
def test_sdk_tagline_off(html_fn):
    assert "tagline: false" in html_fn(sdk=True)
