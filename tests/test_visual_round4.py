"""Round-4 visual tests: the product name must stay visible once the
PayPal pill renders, plus the SDK checkout popup must stay English.

Root cause (round-4 diagnosis, pinned here so it cannot regress):
the old rail max-height of 168px left a 144px content box (168 minus
0.75rem top/bottom rail padding), while a rendered overlay card
needs ~156-171px — 2-line name + price + a 40-55px pill + card
padding. The whole deficit came out of the product name: it is the
only shrinkable element in the card (overflow:hidden gives a flex
item an automatic minimum size of 0), while the price keeps its
1-line minimum and the pill keeps its fixed iframe height. So the
name was visible before the pill rendered (card-buy height 0, no
deficit) and vanished the moment the pill rendered. The fix removes
the rail cap entirely: the rail sizes to content, cards grow upward
from the 64px control clearance, and stretch (default) is kept so
cards stay equal-height with pills aligned at the foot — stretch was
never the clipper, the cap was.
"""
import re

import pytest

from app import embed, pages


def _rule(css, selector):
    m = re.search(re.escape(selector) + r" \{([^}]*)\}", css)
    assert m, f"missing CSS rule: {selector}"
    return m.group(1)


def _rems(rule, prop):
    """All rem numbers of one shorthand/longhand declaration, in order."""
    m = re.search(prop + r":\s*([^;]+);", rule)
    assert m, f"missing declaration: {prop}"
    return [float(x) for x in re.findall(r"([\d.]+)rem", m.group(1))]


def _vertical_pad_rem(rule):
    """Top + bottom padding from a padding shorthand (1-4 values)."""
    vals = _rems(rule, "padding")
    if len(vals) == 1:
        return vals[0] * 2
    if len(vals) == 2:
        return vals[0] * 2
    return vals[0] + vals[2]


def _natural_card_height_px(css):
    """Worst-case rendered overlay-card height from the declared CSS.

    Name: 2 clamped lines. Price: 1 line at the browser's normal
    line-height (~1.2, assumed — the rule declares no line-height).
    Pill: 55px, the tallest PayPal Buttons height, so the guard holds
    even if the SDK renders taller than the configured 40px.
    """
    card = _rule(css, ".overlay-card")
    h3 = _rule(css, ".overlay-card h3")
    price = _rule(css, ".overlay-card .price")
    pad_top, _, pad_bottom = _rems(card, "padding")
    h3_margins = _rems(h3, "margin")
    h3_font = _rems(h3, "font-size")[0]
    h3_lh = float(re.search(r"line-height:\s*([\d.]+)", h3).group(1))
    h3_clamp = int(re.search(r"-webkit-line-clamp:\s*(\d+)", h3).group(1))
    price_margins = _rems(price, "margin")
    price_font = _rems(price, "font-size")[0]
    px = 16.0  # browser default root font size; body declares none
    name = (h3_margins[0] + h3_font * h3_lh * h3_clamp + h3_margins[-1]) * px
    price_h = (price_margins[0] + price_font * 1.2 + price_margins[-1]) * px
    return (pad_top + pad_bottom) * px + name + price_h + 55.0


@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_rail_has_no_height_cap(css):
    # Any max-height on the rail reintroduces the round-4 clip: the
    # rail content box would again fall short of a rendered card.
    assert "max-height" not in _rule(css, ".overlay-rail")


@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_rail_capacity_covers_rendered_card(css):
    # Arithmetic guard for the diagnosis: the old 168px cap left a
    # 144px content box, which is short of a rendered card, so the
    # name — the only shrinkable element — was eaten. With no cap
    # the capacity is unbounded and the inequality always holds; if
    # someone reintroduces a cap below the rendered height, this
    # fails instead of silently clipping the name again.
    rail = _rule(css, ".overlay-rail")
    needed = _natural_card_height_px(css) + _vertical_pad_rem(rail) * 16.0
    assert needed > 144.0  # the old cap's content box could not fit
    m = re.search(r"max-height:\s*([\d.]+)px", rail)
    capacity = float(m.group(1)) if m else float("inf")
    assert capacity >= needed


@pytest.mark.parametrize("css", [embed._CSS, pages._CSS])
def test_card_stack_unchanged_for_name_visibility(css):
    # The fix touches the rail cap only: the card stack that keeps
    # name + price + pill together must stay exactly as pinned.
    h3 = _rule(css, ".overlay-card h3")
    assert "-webkit-line-clamp: 2" in h3
    assert "font-size: 1.05rem" in h3
    assert "margin-top: auto" in _rule(css, ".overlay-card .card-buy")
    assert "overflow: hidden" in _rule(css, ".overlay-card")
    assert "bottom: 64px" in _rule(css, ".overlay-rail")
    assert "justify-content: safe center" in _rule(css, ".overlay-rail")


@pytest.mark.parametrize("script", [embed._sdk_script(), pages._sdk_script()])
def test_sdk_popup_forced_english(script):
    # The sandbox popup otherwise follows the browser locale (Chinese
    # in the round-3 retest) while the demo page is English; locale
    # is a standard SDK parameter, not a workaround.
    assert "locale=en_US" in script
    assert "disable-funding=paylater,card" in script
