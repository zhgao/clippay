"""Second visual polish for the embed and product players.

The first visual redesign got the skeleton right (rounded player,
frosted-glass cards, pill buttons, dechromed embed), but a real
browser read-back still found it short of Apple-grade. This suite
pins the eight fixes from that read-back, on both pages:

1. card + button are one component: the PayPal Buttons container and
   the fallback button live inside a .card-buy area within the card;
2. the floating rail is raised (64px) so no button edge is ever
   pressed or clipped by the progress bar;
3. the fallback button is hidden from first paint in SDK mode and is
   only revealed if the SDK fails to arrive or a render throws;
4. the cancel note is footnote-grade (small, muted), not body text;
5. the PayPal button is silver (not loud gold) and the fallback is a
   neutral grey pill (not the blue rectangle);
6. focus is a thin light ring via :focus-visible, never the browser's
   thick default blue box — and never removed entirely;
7. the rail is centered (safe center keeps narrow-screen scrolling);
8. the embed tab title is generic (no source filename); the product
   page keeps its filename title.

Functional behaviour (popup checkout, fallback takeover, cancel /
blocked / failure classification, rail cap, snap scrolling) is pinned
by the overlay/compact/embed suites — nothing there is deleted.
"""
import re

import pytest

from app import embed, pages

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


def _overlay_card_blocks(html):
    """Split the overlay rail into one segment per card. The rail
    ends at the player-wrap close; each card segment runs from its
    opening tag to the next card's opening tag (or the rail end)."""
    rail_start = html.index('<div class="overlay-rail">')
    rail = html[rail_start:]
    starts = [m.start() for m in re.finditer(r'<div class="card overlay-card">', rail)]
    assert len(starts) == 3
    blocks = []
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(rail)
        blocks.append(rail[s:end])
    return blocks


# -- 1. card + button are one component ---------------------------------

@pytest.mark.parametrize("html_fn", [_embed_html, _product_html])
def test_buttons_live_inside_the_card_component(html_fn):
    for block in _overlay_card_blocks(html_fn()):
        # One buy area inside the card holding both buy paths.
        assert '<div class="card-buy">' in block
        buy_start = block.index('<div class="card-buy">')
        buy = block[buy_start:]
        assert 'class="pp-buttons"' in buy
        assert "fallback-buy" in buy
        # The buy area opens after the name/price, i.e. it is the
        # card's foot — not something floating after the card.
        assert buy_start > block.index("</h3>")


# -- 2. rail raised above the progress bar -------------------------------

@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_rail_raised_to_64px(css):
    assert "bottom: 64px" in css
    assert "bottom: 44px" not in css


# -- 3. fallback hidden by default in SDK mode ---------------------------

@pytest.mark.parametrize("html_fn", [_embed_html, _product_html])
def test_fallback_hidden_by_default_in_sdk_mode(html_fn):
    html = html_fn(sdk=True)
    # Every fallback button ships hidden (embed: 3 overlay cards;
    # product page: 3 overlay + 3 below-video cards); the SDK reveal
    # logic below is the only thing that can show one.
    total = html.count('class="fallback-buy"')
    hidden = html.count('class="fallback-buy" style="display:none"')
    assert total >= 3 and hidden == total
    # Revealed only on SDK failure: exhausted retries, or a render
    # that throws / rejects.
    assert "querySelectorAll('.fallback-buy')" in html
    assert "style.display = 'inline-block'" in html
    assert "rendered.catch" in html
    assert "showFallback(el)" in html


@pytest.mark.parametrize("html_fn", [_embed_html, _product_html])
def test_fallback_stays_visible_without_sdk(html_fn):
    html = html_fn(sdk=False)
    # No SDK script at all, so the fallback is the only buy path and
    # must not ship hidden.
    assert "sdk/js" not in html
    assert 'class="fallback-buy" style="display:none"' not in html
    # Buttons present on both pages (embed: 3 overlay; product page:
    # 3 overlay + 3 below-video), counted by attribute, not by
    # substring — the stylesheet itself also mentions .fallback-buy.
    assert html.count('class="fallback-buy"') >= 3


# -- 4. cancel note at footnote grade ------------------------------------

@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_cancel_note_is_small_and_muted(css):
    m = re.search(r"#msg \{[^}]*\}", css)
    assert m is not None
    assert "font-size: .75rem" in m.group(0)
    assert "color: #8e8e93" in m.group(0)


# -- 5. silver PayPal button, neutral fallback ---------------------------

@pytest.mark.parametrize("html_fn", [_embed_html, _product_html])
def test_paypal_button_is_silver_pill(html_fn):
    html = html_fn()
    assert "color: 'silver'" in html
    assert "shape: 'pill'" in html
    # Still one funding source — silver must not reintroduce the
    # stacked Pay Later / card buttons.
    assert "disable-funding=paylater,card" in html
    assert "fundingSource: paypal.FUNDING.PAYPAL" in html


@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_fallback_button_is_neutral_not_blue(css):
    m = re.search(r"\.fallback-buy \{[^}]*\}", css)
    assert m is not None
    assert "background: #e8e8ed" in m.group(0)
    assert "#0070ba" not in m.group(0)
    # The page's primary buttons deliberately keep the blue.
    assert "button { background: #0070ba" in css


# -- 6. subtle focus ring, never removed ---------------------------------

@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_focus_ring_is_thin_and_light(css):
    assert "button:focus-visible" in css
    assert "outline: 2px solid" in css
    # Focus visibility must never be switched off wholesale.
    assert "outline: none" not in css
    assert "outline: 0" not in css


# -- 7. rail centered, narrow scrolling preserved ------------------------

@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_rail_is_centered_with_safe_fallback(css):
    assert "justify-content: safe center" in css
    # Narrow screens still scroll with snap points.
    assert "overflow-x: auto" in css
    assert "scroll-snap-type: x mandatory" in css


# -- 8. embed tab title is generic ---------------------------------------

def test_embed_title_has_no_filename():
    html = _embed_html()
    assert "<title>Shoppable video · ClipPay</title>" in html
    assert "pitch.mp4" not in html


def test_product_title_keeps_filename():
    html = _product_html()
    assert "<title>pitch.mp4 · ClipPay</title>" in html
