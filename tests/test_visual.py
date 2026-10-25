"""Visual-redesign markers for the embed and product players.

George's verdict on the stacked-up player was "each round looks worse":
features were added one at a time with no overall visual design. This
redesign changes only the visual layer (HTML/CSS/SDK style params) —
no functional logic moves — so these tests pin the look:

- embed page: no visible filename heading (the filename stays only in
  the browser-tab <title>), transparent page background, big rounded
  player card with a soft shadow, dark frosted-glass overlay cards,
  pill-shaped PayPal buttons, tiny muted footnote/brandline, and a
  small restrained mode chip (floating over the video when there is
  one, in flow otherwise);
- product page: the same player treatment, plus soft-shadow info
  cards below the video instead of hard-bordered boxes.

Functional behaviour (rail cap, snap scrolling, single button per
card, cancel/blocked/failure messaging, fallback flow) is pinned by
the overlay/compact/embed suites — nothing there is deleted.
"""
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
]


def _job_dict():
    return {
        "id": "job123",
        "filename": "pitch.mp4",
        "status": "ready",
        "products": [dict(p) for p in PRODUCTS],
    }


def _embed_html(has_video=True):
    return embed.embed_page(
        _job_dict(), "ClipPay", checkout_mode="sandbox",
        has_video=has_video, paypal_client_id="TEST-CLIENT-ID",
    )


def _product_html():
    return pages.product_page(
        _job_dict(), "ClipPay", has_video=True,
        paypal_client_id="TEST-CLIENT-ID",
    )


# -- embed page: dechromed ----------------------------------------------

def test_embed_page_has_no_visible_filename_heading():
    html = _embed_html()
    assert "<h1>" not in html
    # The player, rail, and buy flow are untouched by the redesign.
    assert "<video" in html
    assert '<div class="overlay-rail">' in html
    assert "Buy with PayPal" in html


def test_embed_page_background_is_transparent():
    assert "background: transparent" in embed._CSS


def test_embed_mode_chip_is_small_and_restrained():
    assert "font-size: .72rem" in embed._CSS
    assert "border-radius: 999px" in embed._CSS
    # Floating over the video when there is one…
    assert 'class="badge badge-float"' in _embed_html(has_video=True)
    # …in flow when there is no video to float over.
    assert '<p><span class="badge">' in _embed_html(has_video=False)


def test_embed_footnote_and_brandline_are_tiny_and_muted():
    assert "font-size: .75rem" in embed._CSS
    assert "color: #8e8e93" in embed._CSS
    assert "font-size: .72rem" in embed._CSS


# -- player card + frosted-glass overlay cards, both pages --------------

@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_player_wrap_is_big_rounded_soft_shadow(css):
    assert "border-radius: 18px" in css
    assert "box-shadow: 0 16px 48px rgba(0,0,0,.20)" in css
    assert "overflow: hidden" in css


@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_overlay_cards_are_dark_frosted_glass(css):
    assert "background: rgba(20,20,28,.55)" in css
    assert "backdrop-filter: blur(16px)" in css
    assert "border-radius: 16px" in css
    # White text on the dark glass, price prominent.
    assert "color: #fff" in css


@pytest.mark.parametrize("html_fn", [_embed_html, _product_html])
def test_paypal_buttons_are_pill_shaped(html_fn):
    html = html_fn()
    assert "shape: 'pill'" in html
    assert "height: 40" in html
    # One funding source only, as before — the pill shape must not
    # reintroduce the stacked funding buttons.
    assert "disable-funding=paylater,card" in html
    assert "fundingSource: paypal.FUNDING.PAYPAL" in html


# -- product page: same player language, soft info cards -----------------

def test_product_page_keeps_its_heading_but_restyled():
    html = _product_html()
    # Standalone page keeps a heading (unlike the chromeless embed);
    # it is a big title now, not the old small one.
    assert "<h1>pitch.mp4</h1>" in html
    assert "font-size: 2rem" in pages._CSS


def test_product_page_info_cards_are_soft_not_hard_bordered():
    assert "border: 1px solid #ddd" not in pages._CSS
    assert "border-radius: 16px" in pages._CSS
    assert "box-shadow: 0 4px 24px rgba(0,0,0,.08)" in pages._CSS
    # Full info still lives below the video.
    html = _product_html()
    assert "A handmade ceramic mug." in html
    assert "Mentioned at" in html
