"""Embeddable minimal player (GET /embed/{job_id}).

A creator copies one iframe snippet from the product page and pastes it
into their own website; shoppers then buy right there, without being
sent to another site. This page therefore has no navigation chrome at
all: no dashboard link, no landing link, no anchors — just the product
cards and their buy buttons.

Buy flow mirrors the demo player exactly: the unchanged M1
`POST /api/orders` path first (real PayPal Sandbox checkout when
credentials are configured), falling back only to the explicitly
labelled mock checkout (`POST /api/watch/demo/checkout`) when that path
fails. The mock order is never written to the orders table.

Honesty note on the tote bag, same as the demo player: its $12.00 was
an inferred price — the audio did not clearly state it. When the tote
bag is among the products, the footnote below says so in plain
language; this page never claims the video spoke that price.
"""
import html
import json

from .checkout_errors import (
    BLOCKED_KEYWORDS,
    BLOCKED_MESSAGE,
    CANCEL_KEYWORDS,
    CANCEL_MESSAGE,
)

_CSS = """
/* Apple-store-minimal visual language for the embed player: the page
   itself is transparent (it lives inside other people's sites), the
   player is one big rounded card with a soft shadow, and the overlay
   cards are dark frosted glass — no hard white boxes, no loud chrome.
   All functional markers stay exactly as the tests pin them: rail
   height cap, control-bar clearance, snap scrolling, one PayPal
   button per card. */
body { font-family: system-ui, -apple-system, sans-serif; margin: 0;
       padding: 0 1rem 1rem; background: transparent; color: #1a1a2e; }
.badge { display: inline-block; background: rgba(20,20,28,.55); color: #fff;
         -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
         border: 0; border-radius: 999px; padding: .35rem .8rem;
         font-size: .72rem; letter-spacing: .01em; }
.badge-float { position: absolute; top: .75rem; left: .75rem; z-index: 2;
         pointer-events: none; }
.card { border: 0; border-radius: 16px; padding: 1.25rem 1.5rem;
        margin: 1rem 0; background: #fff;
        box-shadow: 0 4px 24px rgba(0,0,0,.08); }
.price { font-size: 1.25rem; font-weight: 700; }
.ts { color: #8e8e93; font-size: .85rem; }
.note { color: #8e8e93; font-size: .75rem; }
button { background: #0070ba; color: #fff; border: 0; border-radius: 999px;
         padding: .6rem 1.2rem; font-size: 1rem; cursor: pointer; }
button:disabled { opacity: .5; }
/* Compact overlay rail: product cards float over the bottom of the
   video so a shopper can tap to buy while watching, without leaving
   the video. The rail itself ignores clicks (video controls stay
   usable) and only the cards respond. It sits above the control bar
   (~44px) so it never covers play/seek, and its height is capped so
   the video body stays visible: overlay cards carry name + price +
   one PayPal button only — no long description, no timestamp line.
   Cards are always visible — never gated per second, because
   transcription timestamps are too coarse to trigger on. The rail
   scrolls horizontally with snap points and end padding, so the last
   card always slides fully into view instead of stopping half-cut at
   the edge. */
.player-wrap { position: relative; border-radius: 18px; overflow: hidden;
         background: #000; box-shadow: 0 16px 48px rgba(0,0,0,.20); }
.player-wrap video { display: block; width: 100%; }
.overlay-rail { position: absolute; left: 0; right: 0; bottom: 44px;
         display: flex; gap: .75rem; overflow-x: auto; overflow-y: hidden;
         padding: .75rem 1rem; max-height: 132px;
         box-sizing: border-box; scroll-snap-type: x mandatory;
         scroll-padding-right: 1rem; pointer-events: none; }
.overlay-card { pointer-events: auto; flex: 0 0 180px; scroll-snap-align: start;
         background: rgba(20,20,28,.55);
         -webkit-backdrop-filter: blur(16px) saturate(1.3);
         backdrop-filter: blur(16px) saturate(1.3);
         border: 1px solid rgba(255,255,255,.16);
         border-radius: 16px; padding: .8rem .9rem;
         box-shadow: 0 8px 28px rgba(0,0,0,.35); color: #fff; }
.overlay-card h3 { margin: .25rem 0; font-size: .95rem; white-space: nowrap;
         overflow: hidden; text-overflow: ellipsis; color: #fff; }
.overlay-card .price { font-size: 1.15rem; margin: .35rem 0 .5rem; color: #fff; }
.confirm { border: 0; border-radius: 16px; padding: 1rem 1.25rem;
           background: #f1f8f1; box-shadow: 0 4px 24px rgba(0,0,0,.08); }
.err { color: #b00020; }
.brandline { color: #8e8e93; font-size: .72rem; margin-top: 1rem; }
"""


def _fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _card_html(product: dict, sdk: bool, overlay: bool) -> str:
    """One product card. In SDK mode it also carries the PayPal Buttons
    container; the fallback Buy button stays in the markup and is only
    hidden by JS once the SDK actually renders, so a failed SDK load
    leaves the old redirect-or-mock flow intact."""
    name = html.escape(product.get("name", ""))
    desc = html.escape(product.get("description", ""))
    price = html.escape(str(product.get("price", "")))
    ts = _fmt_ts(float(product.get("timestamp_seconds", 0)))
    buy_arg = json.dumps(
        {"amount": str(product.get("price", "")), "description": product.get("name", "")}
    )
    buy_arg = (
        buy_arg.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("'", "\\u0027")
    )
    cls = "card overlay-card" if overlay else "card"
    pp = ""
    if sdk:
        pp = (
            f'<div class="pp-buttons" '
            f'data-amount="{html.escape(str(product.get("price", "")), quote=True)}" '
            f'data-description="{html.escape(product.get("name", ""), quote=True)}"></div>'
        )
    if overlay:
        # Compact overlay card: name + price + buy only. The long
        # description and the timestamp line would push the card to
        # nearly the full video height and cover the video itself.
        return (
            f'<div class="{cls}"><h3>{name}</h3>'
            f'<p class="price">${price}</p>'
            f"{pp}<button class=\"fallback-buy\" "
            f"onclick='buy(this, {buy_arg})'>Buy with PayPal</button>"
            f"</div>"
        )
    return (
        f'<div class="{cls}"><h3>{name}</h3>'
        f"<p>{desc}</p>"
        f'<p class="price">${price}</p>'
        f'<p class="ts">Mentioned at {ts} in the video</p>'
        f"{pp}<button class=\"fallback-buy\" "
        f"onclick='buy(this, {buy_arg})'>Buy with PayPal</button>"
        f"</div>"
    )


def _sdk_script() -> str:
    """PayPal JS SDK popup checkout. Only rendered when server-side
    credentials are configured (sandbox mode + client id).

    The client id is PayPal's public identifier — the SDK is designed
    to live in the page. The Secret never leaves the server: order
    creation and capture keep going through the existing M1 endpoints.
    If the SDK never loads, this script simply never runs and the
    fallback Buy buttons stay visible.

    One PayPal button per card only: the SDK URL disables the
    paylater and card funding sources and Buttons is pinned to the
    PayPal funding source, so the overlay cards stay compact instead
    of stacking three tall buttons each.

    Error display distinguishes a cancel from a real failure: the SDK
    reports a closed popup as an error ("Window is closed, can not
    determine type"), which must not show as a red failure. The
    keyword lists come from app.checkout_errors — the same lists the
    unit tests cover — rendered into this script verbatim.
    """
    script = """
<script src="https://www.paypal.com/sdk/js?client-id=CLIENT_ID&currency=USD&disable-funding=paylater,card" async></script>
<script>
(function () {
  function classifyCheckoutError(raw) {
    var m = ((raw || '') + '').toLowerCase();
    var cancelKeys = %%CANCEL_KEYS%%;
    for (var i = 0; i < cancelKeys.length; i++) {
      if (m.indexOf(cancelKeys[i]) !== -1) return 'cancel';
    }
    var blockedKeys = %%BLOCKED_KEYS%%;
    for (var j = 0; j < blockedKeys.length; j++) {
      if (m.indexOf(blockedKeys[j]) !== -1) return 'blocked';
    }
    return 'failure';
  }
  var tries = 0;
  function init() {
    if (window.paypal && window.paypal.Buttons) {
      document.querySelectorAll('.pp-buttons').forEach(function (el) {
        var amount = el.getAttribute('data-amount');
        var desc = el.getAttribute('data-description');
        var fallback = el.parentElement.querySelector('.fallback-buy');
        if (fallback) fallback.style.display = 'none';
        paypal.Buttons({
          fundingSource: paypal.FUNDING.PAYPAL,
          style: { shape: 'pill', height: 40 },
          createOrder: function () {
            return fetch('/api/orders', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({amount: amount, currency: 'USD',
                                    description: desc})
            }).then(function (r) {
              return r.json().then(function (d) {
                if (!r.ok || !d.order_id) throw new Error(d.detail || 'order failed');
                return d.order_id;
              });
            });
          },
          onApprove: function (data) {
            return fetch('/api/orders/' + encodeURIComponent(data.orderID) + '/capture', {method: 'POST'})
              .then(function (r) { return r.json(); })
              .then(function (d) {
                var confirm = document.getElementById('confirm');
                confirm.innerHTML = '<h3>Payment complete</h3>'
                  + '<p><b>' + desc + '</b> — $' + amount + '</p>'
                  + '<p>PayPal order: ' + data.orderID + '</p>'
                  + '<p>Status: ' + (d.status || 'COMPLETED') + '</p>';
                confirm.className = 'confirm';
                confirm.style.display = 'block';
              });
          },
          onCancel: function () {
            document.getElementById('msg').textContent = %%CANCEL_MSG%%;
          },
          onError: function (err) {
            var msg = document.getElementById('msg');
            var kind = classifyCheckoutError(err && err.message);
            if (kind === 'cancel') {
              msg.textContent = %%CANCEL_MSG%%;
            } else if (kind === 'blocked') {
              msg.textContent = %%BLOCKED_MSG%%;
            } else {
              msg.innerHTML = '<span class="err">Checkout failed: '
                + (err && err.message ? err.message : 'unknown error') + '</span>';
            }
          }
        }).render(el);
      });
      return;
    }
    if (++tries < 50) setTimeout(init, 100);
    // SDK never arrived — the fallback Buy buttons stay visible.
  }
  init();
})();
</script>
"""
    return (
        script.replace("%%CANCEL_KEYS%%", json.dumps(list(CANCEL_KEYWORDS), ensure_ascii=False))
        .replace("%%BLOCKED_KEYS%%", json.dumps(list(BLOCKED_KEYWORDS), ensure_ascii=False))
        .replace("%%CANCEL_MSG%%", json.dumps(CANCEL_MESSAGE, ensure_ascii=False))
        .replace("%%BLOCKED_MSG%%", json.dumps(BLOCKED_MESSAGE, ensure_ascii=False))
    )


def embed_page(job: dict, brand: str, checkout_mode: str = "demo",
               has_video: bool = False, paypal_client_id: str = "") -> str:
    """Render the chromeless embeddable player for one ready job.

    When the job has a video, the product cards ride as a horizontal
    rail overlaid on the bottom of the video (above the control bar),
    always visible — never gated per second. In sandbox mode the cards
    check out through a PayPal JS SDK popup that never leaves the
    video page; without credentials the old redirect-or-mock flow
    stays. Jobs without a video keep the classic below-video cards.
    """
    title = job.get("filename") or "Video"
    status = job.get("status", "")
    if checkout_mode == "sandbox":
        badge = "Sandbox checkout — PayPal Sandbox, no real money moves."
    else:
        badge = "Demo mode — mock checkout, no real payment is made."
    # Dechromed: no filename heading on the embed page — it lives in
    # other people's sites, so the player itself is the whole page.
    # The mode chip floats over the video's top-left corner when there
    # is a video, and sits in flow otherwise. The filename stays only
    # in the <title> tag (browser tab), never as visible chrome.
    badge_span = f'<span class="badge">{badge}</span>'
    parts = []
    if status != "ready":
        parts.append(f"<p>{badge_span}</p>")
        detail = html.escape(job.get("error") or f"status: {status}")
        parts.append(f'<p class="err">This player is not ready yet — {detail}</p>')
        body = "".join(parts)
        return _wrap(title, brand, body)

    sdk = checkout_mode == "sandbox" and bool(paypal_client_id)
    products = job.get("products") or []
    if has_video:
        video_url = f"/api/jobs/{html.escape(job.get('id', ''))}/video"
        video_tag = (
            f'<video controls playsinline preload="metadata" '
            f'style="width:100%" src="{video_url}"></video>'
        )
        chip = f'<span class="badge badge-float">{badge}</span>'
        if products:
            rail = "".join(_card_html(p, sdk, overlay=True) for p in products)
            parts.append(
                f'<div class="player-wrap">{chip}{video_tag}'
                f'<div class="overlay-rail">{rail}</div></div>'
            )
        else:
            parts.append(f'<div class="player-wrap">{chip}{video_tag}</div>')
    else:
        parts.append(f"<p>{badge_span}</p>")
    if not products:
        parts.append("<p>No purchasable products were found in this video.</p>")
    elif not has_video:
        parts.extend(_card_html(p, sdk, overlay=False) for p in products)
    has_tote = any(p.get("name") == "Organic Cotton Tote Bag" for p in products)
    if has_tote:
        parts.append(
            '<p class="note">Note: the Organic Cotton Tote Bag\'s $12.00 was '
            "inferred during extraction — the audio did not clearly state "
            "that price, and this page does not claim the video spoke it.</p>"
        )
    parts.append("""
<div id="confirm" style="display:none"></div>
<p id="msg"></p>
<script>
async function buy(btn, payload) {
  const msg = document.getElementById('msg');
  const confirm = document.getElementById('confirm');
  btn.disabled = true;
  btn.textContent = 'Checking out…';
  msg.textContent = '';
  confirm.style.display = 'none';
  // Real path first: the unchanged M1 orders endpoint. With PayPal
  // Sandbox credentials configured it returns an approval URL and the
  // buyer continues to PayPal. Without credentials it fails, and only
  // then do we fall back to the explicitly labelled mock checkout.
  try {
    const r = await fetch('/api/orders', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({amount: payload.amount, currency: 'USD',
                            description: payload.description})
    });
    const data = await r.json();
    if (r.ok && data.approve_url) {
      window.location = data.approve_url;
      return;
    }
    throw new Error(data.detail || 'real checkout unavailable');
  } catch (err) {
    try {
      const r2 = await fetch('/api/watch/demo/checkout', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({amount: payload.amount,
                              description: payload.description})
      });
      const mock = await r2.json();
      if (!r2.ok) throw new Error(mock.detail || 'demo checkout failed');
      confirm.innerHTML = '<h3>Demo checkout complete</h3>'
        + '<p><b>' + mock.description + '</b> — $' + mock.amount + '</p>'
        + '<p>Mock order: ' + mock.order_id + '</p>'
        + '<p><b>This was a mock checkout. No real PayPal payment was '
        + 'made or charged.</b></p>';
      confirm.className = 'confirm';
      confirm.style.display = 'block';
    } catch (err2) {
      msg.innerHTML = '<span class="err">Checkout failed: '
        + err2.message + '</span>';
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Buy with PayPal';
  }
}
</script>
""")
    if sdk:
        # The client id is PayPal's public identifier; the Secret never
        # enters the page — order creation and capture stay server-side.
        parts.append(
            _sdk_script().replace(
                "CLIENT_ID", html.escape(paypal_client_id, quote=True)
            )
        )
    body = "".join(parts)
    return _wrap(title, brand, body)


def _wrap(title: str, brand: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)} · {html.escape(brand)}</title>"
        f"<style>{_CSS}</style></head><body>{body}"
        f'<p class="brandline">Powered by {html.escape(brand)}</p>'
        "</body></html>"
    )
