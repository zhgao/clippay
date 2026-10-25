"""Server-rendered HTML pages: landing/upload, shoppable product page,
and the seller dashboard. Plain string templates with everything escaped;
the checkout button calls the M1 `POST /api/orders` JSON flow and redirects
the buyer to the returned PayPal approval URL.
"""
import html
import json
import time

from .checkout_errors import (
    BLOCKED_KEYWORDS,
    BLOCKED_MESSAGE,
    CANCEL_KEYWORDS,
    CANCEL_MESSAGE,
)

_CSS = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 760px;
       padding: 0 1rem; color: #1a1a2e; }
h1 { font-size: 1.6rem; } h2 { margin-top: 2rem; }
.card { border: 1px solid #ddd; border-radius: 10px; padding: 1rem 1.25rem;
        margin: 1rem 0; }
.price { font-size: 1.25rem; font-weight: 700; }
.ts { color: #666; font-size: .85rem; }
button { background: #0070ba; color: #fff; border: 0; border-radius: 6px;
         padding: .6rem 1.2rem; font-size: 1rem; cursor: pointer; }
button:disabled { opacity: .5; }
.confirm { border: 2px solid #2e7d32; border-radius: 10px; padding: 1rem 1.25rem;
           background: #f1f8f1; }
/* Same compact overlay rail as the embed player: cards float over
   the bottom of the video (above the control bar) so shoppers buy
   while watching. The rail ignores clicks except on the cards
   themselves, its height is capped so the video body stays visible,
   and cards are always visible — never gated per second. Overlay
   cards carry name + price + one PayPal button only; the full
   product info (description, timestamp) lives in the cards below the
   video on this page. The rail scrolls horizontally with snap points
   and end padding, so the last card always slides fully into view. */
.player-wrap { position: relative; }
.player-wrap video { display: block; }
.overlay-rail { position: absolute; left: 0; right: 0; bottom: 44px;
         display: flex; gap: .5rem; overflow-x: auto; overflow-y: hidden;
         padding: .5rem .75rem .5rem .5rem; max-height: 132px;
         box-sizing: border-box; scroll-snap-type: x mandatory;
         scroll-padding-right: .75rem; pointer-events: none; }
.overlay-card { pointer-events: auto; flex: 0 0 180px; scroll-snap-align: start;
         background: rgba(255,255,255,.95);
         border-radius: 10px; padding: .6rem .75rem; box-shadow: 0 2px 12px rgba(0,0,0,.35); }
.overlay-card h3 { margin: .25rem 0; font-size: .95rem; white-space: nowrap;
         overflow: hidden; text-overflow: ellipsis; }
.overlay-card .price { font-size: 1.05rem; margin: .25rem 0; }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid #e5e5e5; padding: .45rem .5rem;
         text-align: left; font-size: .92rem; }
.err { color: #b00020; }
footer { margin-top: 3rem; color: #888; font-size: .8rem; }
"""


def _fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _fmt_time(epoch: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch))


def _page(title: str, brand: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)} · {html.escape(brand)}</title>"
        f"<style>{_CSS}</style></head><body>{body}"
        f"<footer>{html.escape(brand)} — turn any video into a checkout page.</footer>"
        "</body></html>"
    )


def landing_page(brand: str) -> str:
    body = f"""
<h1>{html.escape(brand)}</h1>
<p>Upload a product or tutorial video. {html.escape(brand)} transcribes it,
an AI agent extracts the products mentioned, and you get a shoppable page
where every item can be bought with PayPal.</p>
<form id="upload-form">
  <input type="file" id="file" accept="video/mp4,.mp4" required>
  <button type="submit">Upload &amp; analyze</button>
</form>
<h2>Or paste a video link — no upload needed</h2>
<form id="url-form">
  <input type="url" id="video-url" size="48"
         placeholder="YouTube, TikTok, or Instagram video URL" required>
  <button type="submit">Import &amp; analyze</button>
</form>
<p class="ts">YouTube captions are tried first (most reliable). TikTok and
Instagram go through a download step, which is best-effort — those
platforms may block automated downloads, so imports there are not
guaranteed to succeed.</p>
<h2>Just want to see it work?</h2>
<p><button id="sample-btn" type="button">Try the demo instantly — no upload
needed</button></p>
<p id="msg"></p>
<p><a href="/dashboard">Seller dashboard</a></p>
<script>
document.getElementById('upload-form').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const msg = document.getElementById('msg');
  const file = document.getElementById('file').files[0];
  if (!file) return;
  msg.textContent = 'Uploading and analyzing… this can take a moment.';
  const fd = new FormData();
  fd.append('file', file);
  try {{
    const r = await fetch('/api/videos', {{method: 'POST', body: fd}});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'upload failed');
    window.location = '/p/' + data.id;
  }} catch (err) {{
    msg.innerHTML = '<span class="err">' + err.message + '</span>';
  }}
}});
document.getElementById('url-form').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const msg = document.getElementById('msg');
  const url = document.getElementById('video-url').value.trim();
  if (!url) return;
  msg.textContent = 'Importing and analyzing… this can take a moment.';
  try {{
    const r = await fetch('/api/videos/from-url', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{url: url}})
    }});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'import failed');
    window.location = '/p/' + data.id;
  }} catch (err) {{
    msg.innerHTML = '<span class="err">' + err.message + '</span>';
  }}
}});
document.getElementById('sample-btn').addEventListener('click', async () => {{
  const msg = document.getElementById('msg');
  msg.textContent = 'Running the built-in sample…';
  try {{
    const r = await fetch('/api/videos/sample', {{method: 'POST'}});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'sample failed');
    window.location = '/sample/' + data.id;
  }} catch (err) {{
    msg.innerHTML = '<span class="err">' + err.message + '</span>';
  }}
}});
</script>
"""
    return _page("Upload a video", brand, body)


def _product_card_html(product: dict, sdk: bool, overlay: bool) -> str:
    """One product card; mirrors the embed player's card. In SDK mode
    it also carries the PayPal Buttons container, and the fallback Buy
    button is only hidden by JS once the SDK actually renders."""
    name = html.escape(product.get("name", ""))
    desc = html.escape(product.get("description", ""))
    price = html.escape(str(product.get("price", "")))
    ts = _fmt_ts(float(product.get("timestamp_seconds", 0)))
    buy_arg = json.dumps(
        {"amount": str(product.get("price", "")), "description": product.get("name", "")}
    )
    # The JSON sits inside an HTML attribute: escape the characters
    # that could break out of it (JS string literals decode \uXXXX).
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
        # Compact overlay card: name + price + buy only (same rule as
        # the embed player — description and timestamp would cover
        # the video). Full info lives in the below-video cards.
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
    """PayPal JS SDK popup checkout; same contract as the embed
    player. The client id is PayPal's public identifier; the Secret
    never enters the page. If the SDK never loads, the fallback Buy
    buttons stay visible and keep the old redirect flow.

    One PayPal button per card only (disable-funding on the SDK URL
    plus a pinned PayPal funding source), and the same cancel/blocked/
    failure classification as the embed player — a closed popup is a
    neutral cancel note, never a red failure."""
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


def product_page(job: dict, brand: str, has_video: bool = False,
                 paypal_client_id: str = "") -> str:
    title = job.get("filename") or "Video"
    status = job.get("status", "")
    parts = [f"<h1>{html.escape(title)}</h1>"]
    if status != "ready":
        detail = html.escape(job.get("error") or f"status: {status}")
        parts.append(f'<p class="err">This page is not ready yet — {detail}</p>')
        parts.append('<p><a href="/dashboard">Seller dashboard</a></p>')
        return _page(title, brand, "".join(parts))

    sdk = bool(paypal_client_id)
    products = job.get("products") or []
    if has_video:
        video_url = f"/api/jobs/{html.escape(job.get('id', ''))}/video"
        video_tag = (
            f'<video controls playsinline preload="metadata" '
            f'style="width:100%" src="{video_url}"></video>'
        )
        if products:
            rail = "".join(_product_card_html(p, sdk, overlay=True) for p in products)
            parts.append(
                f'<div class="player-wrap">{video_tag}'
                f'<div class="overlay-rail">{rail}</div></div>'
            )
        else:
            parts.append(video_tag)
    if not products:
        parts.append("<p>No purchasable products were found in this video.</p>")
    else:
        # Full product info below the video when there is one: the
        # overlay cards above are compact by design (name + price +
        # buy only), so the description and timestamp live here.
        parts.extend(_product_card_html(p, sdk, overlay=False) for p in products)
    if sdk:
        parts.append('<div id="confirm" style="display:none"></div><p id="msg"></p>')
    embed_job_id = json.dumps(job.get("id", ""))
    parts.append(f"""
<h2>Embed on your website</h2>
<p>Copy once, paste it into your own website — shoppers buy right there,
no detour to another site.</p>
<textarea id="embed-code" readonly rows="3" style="width:100%"></textarea>
<p><button id="copy-embed" type="button">Copy embed code</button>
<span id="copy-msg"></span></p>
<script>
(function () {{
  var code = document.getElementById('embed-code');
  code.value = '<iframe src="' + window.location.origin + '/embed/'
    + {embed_job_id} + '" width="100%" height="540" frameborder="0" '
    + 'allowfullscreen></iframe>';
  document.getElementById('copy-embed').addEventListener('click', async () => {{
    var msg = document.getElementById('copy-msg');
    try {{
      await navigator.clipboard.writeText(code.value);
      msg.textContent = 'Copied!';
    }} catch (e) {{
      code.select();
      document.execCommand('copy');
      msg.textContent = 'Copied!';
    }}
  }});
}})();
</script>
""")
    parts.append("""
<script>
async function buy(btn, payload) {
  btn.disabled = true;
  btn.textContent = 'Creating order…';
  try {
    const r = await fetch('/api/orders', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({amount: payload.amount, currency: 'USD',
                            description: payload.description})
    });
    const data = await r.json();
    if (!r.ok || !data.approve_url) throw new Error(data.detail || 'checkout failed');
    window.location = data.approve_url;
  } catch (err) {
    btn.disabled = false;
    btn.textContent = 'Buy with PayPal';
    alert('Checkout failed: ' + err.message);
  }
}
</script>
""")
    if sdk:
        # Client id only — the Secret never enters the page.
        parts.append(
            _sdk_script().replace(
                "CLIENT_ID", html.escape(paypal_client_id, quote=True)
            )
        )
    parts.append('<p><a href="/dashboard">Seller dashboard</a></p>')
    return _page(title, brand, "".join(parts))


def dashboard_page(jobs: list[dict], orders: list[dict], brand: str) -> str:
    parts = [f"<h1>{html.escape(brand)} — Seller dashboard</h1>"]
    parts.append("<h2>Videos</h2>")
    if not jobs:
        parts.append("<p>No videos yet. <a href=\"/\">Upload one</a>.</p>")
    else:
        rows = []
        for job in jobs:
            rows.append(
                "<tr>"
                f"<td>{_fmt_time(job['created_at'])}</td>"
                f"<td>{html.escape(job.get('filename', ''))}</td>"
                f"<td>{html.escape(job.get('status', ''))}</td>"
                f"<td>{len(job.get('products') or [])}</td>"
                f"<td><a href=\"/p/{html.escape(job['id'])}\">page</a></td>"
                "</tr>"
            )
        parts.append(
            "<table><tr><th>Uploaded</th><th>File</th><th>Status</th>"
            "<th>Products</th><th></th></tr>" + "".join(rows) + "</table>"
        )
    parts.append("<h2>Orders</h2>")
    if not orders:
        parts.append("<p>No orders yet.</p>")
    else:
        rows = []
        for order in orders:
            rows.append(
                "<tr>"
                f"<td>{_fmt_time(order['created_at'])}</td>"
                f"<td>{html.escape(order.get('paypal_order_id', ''))}</td>"
                f"<td>{html.escape(order.get('description') or '')}</td>"
                f"<td>{html.escape(order.get('currency', 'USD'))} "
                f"{html.escape(order.get('amount', ''))}</td>"
                f"<td>{html.escape(order.get('status', ''))}</td>"
                f"<td>{html.escape(order.get('payer_email') or '')}</td>"
                "</tr>"
            )
        parts.append(
            "<table><tr><th>Created</th><th>PayPal order</th><th>Item</th>"
            "<th>Amount</th><th>Status</th><th>Buyer</th></tr>"
            + "".join(rows) + "</table>"
        )
    return _page("Dashboard", brand, "".join(parts))
