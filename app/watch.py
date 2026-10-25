"""Demo in-video shopping player (GET /watch/demo).

Purely additive demo page: it does NOT touch the M1 orders code, the M2
video pipeline, /p/{job_id}, or the dashboard. It reuses the existing
M1 `POST /api/orders` checkout path unchanged, and only falls back to an
explicitly labelled mock checkout (POST /api/watch/demo/checkout) when
that path fails — e.g. when no PayPal credentials are configured, which
is the normal state for a credential-free demo.

Product data
------------
The three products below are the exact results verified on 2026-10-24
from the real extraction run, names and prices verbatim:

  * Handmade Ceramic Mug — $20.00
  * Walnut Cutting Board — $45.00
  * Organic Cotton Tote Bag — $12.00

Honesty note on the tote bag: its $12.00 was an inferred price — the
audio did not clearly state it. This page therefore never claims the
video spoke that price; it only shows the product name and price, and
the footnote below the products says so in plain language.

Buyability
----------
All three products are shown beside the video for the whole playback
(deliberately NOT gated on per-second timestamps: the existing
transcript timestamps are coarse — a 22-second pitch collapses into a
single segment — so timestamp-gated tags would be theatre, not signal).

Video track
-----------
`data/samples/pitch.mp4` and `data/samples/jfk.mp4` both turned out to
have all-black video tracks (mean frame brightness 0.0 at every sampled
timestamp; audio-led files). Neither is usable as player footage, so the
demo video is synthesized by `scripts/generate_demo_watch_video.sh`:
product-card slides (one per product, name + price) over the real
`pitch.mp4` audio track, written to
`data/samples/demo_watch.mp4`. That .mp4 is a binary asset and cannot be
pushed through the GitHub connector's UTF-8-only snapshot push, so it is
NOT committed here: clone the repo and run the generator script once to
recreate it locally. When the file is absent, the page shows an animated
product-slide fallback in the same frame instead of a broken player, so
the page still demos end to end.
"""
import html
import json
import os

DEMO_PRODUCTS = [
    {
        "name": "Handmade Ceramic Mug",
        "description": "Handmade ceramic mug, featured in the demo pitch.",
        "price": "20.00",
    },
    {
        "name": "Walnut Cutting Board",
        "description": "Walnut cutting board, featured in the demo pitch.",
        "price": "45.00",
    },
    {
        "name": "Organic Cotton Tote Bag",
        "description": "Organic cotton tote bag, featured in the demo pitch.",
        "price": "12.00",
    },
]

# Default location of the synthesized demo video, resolved from this file
# so it works regardless of the process working directory.
DEFAULT_DEMO_VIDEO_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "samples", "demo_watch.mp4")
)

_CSS = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 980px;
       padding: 0 1rem; color: #1a1a2e; }
.badge { display: inline-block; background: #fff3cd; border: 1px solid #e6c87a;
         border-radius: 999px; padding: .25rem .8rem; font-size: .85rem; }
.layout { display: flex; gap: 1.5rem; align-items: flex-start; flex-wrap: wrap; }
.player { flex: 1 1 480px; }
video { width: 100%; border-radius: 12px; background: #111; display: block; }
.fallback { display: none; width: 100%; aspect-ratio: 16 / 9; border-radius: 12px;
            overflow: hidden; position: relative; background: #111; }
.fallback.on { display: block; }
.slide { position: absolute; inset: 0; display: flex; flex-direction: column;
         align-items: center; justify-content: center; color: #fff;
         opacity: 0; animation: slidecycle 22.5s infinite; font-size: 1.4rem; }
.slide:nth-child(1) { background: #8c4a3c; animation-delay: 0s; }
.slide:nth-child(2) { background: #5a4632; animation-delay: 7.5s; }
.slide:nth-child(3) { background: #3f5a44; animation-delay: 15s; }
.slide b { font-size: 1.8rem; }
@keyframes slidecycle {
  0% { opacity: 0; } 2% { opacity: 1; } 31% { opacity: 1; } 33.5% { opacity: 0; }
  100% { opacity: 0; }
}
.sidebar { flex: 0 1 300px; display: flex; flex-direction: column; gap: 1rem; }
.card { border: 1px solid #ddd; border-radius: 10px; padding: 1rem 1.25rem; }
.price { font-size: 1.25rem; font-weight: 700; }
.note { color: #666; font-size: .85rem; }
button { background: #0070ba; color: #fff; border: 0; border-radius: 6px;
         padding: .6rem 1.2rem; font-size: 1rem; cursor: pointer; }
button:disabled { opacity: .5; }
.confirm { border: 2px solid #2e7d32; border-radius: 10px; padding: 1rem 1.25rem;
           background: #f1f8f1; }
.err { color: #b00020; }
footer { margin-top: 3rem; color: #888; font-size: .8rem; }
"""


def watch_page(brand: str, checkout_mode: str = "demo") -> str:
    """Render the demo player page.

    checkout_mode is "demo" when no PayPal credentials are configured
    (mock checkout, honestly labelled) or "sandbox" when the real
    PayPal Sandbox path is available. It only changes the badge copy;
    the buy flow itself always tries the real M1 /api/orders first.
    """
    if checkout_mode == "sandbox":
        badge = "Sandbox checkout — PayPal Sandbox, no real money moves."
    else:
        badge = "Demo mode — mock checkout, no real payment is made."
    cards = []
    for product in DEMO_PRODUCTS:
        name = html.escape(product["name"])
        desc = html.escape(product["description"])
        price = html.escape(product["price"])
        buy_arg = json.dumps(
            {"amount": product["price"], "description": product["name"]}
        )
        buy_arg = (
            buy_arg.replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("'", "\\u0027")
        )
        cards.append(
            f'<div class="card" data-product="{name}">'
            f"<h3>{name}</h3><p>{desc}</p>"
            f'<p class="price">${price}</p>'
            f"<button onclick='buy(this, {buy_arg})'>Buy</button>"
            f"</div>"
        )
    slides = "".join(
        f'<div class="slide"><b>{html.escape(p["name"])}</b>'
        f'<span>${html.escape(p["price"])}</span></div>'
        for p in DEMO_PRODUCTS
    )
    body = f"""
<h1>{html.escape(brand)} — In-video shopping demo</h1>
<p><span class="badge">{badge}</span></p>
<p><button id="sample-btn" type="button">Try the sample instantly — no upload
needed</button> <span id="sample-msg" class="note"></span></p>
<div class="layout">
  <div class="player">
    <video id="demo-video" controls autoplay muted loop playsinline
           src="/watch/demo/video"></video>
    <div class="fallback" id="fallback">{slides}</div>
    <p class="note">Products stay buyable for the whole video — no
    timestamp gating. If the demo video file is not present on this
    server, the animated product slides above play instead.</p>
  </div>
  <div class="sidebar">{''.join(cards)}</div>
</div>
<div id="confirm" style="display:none"></div>
<p id="msg"></p>
<p class="note">Prices are shown as listed for this demo. Note: the
Organic Cotton Tote Bag's $12.00 was inferred during extraction — the
audio did not clearly state that price, and this page does not claim
the video spoke it.</p>
<p><a href="/dashboard">Seller dashboard</a></p>
<script>
document.getElementById('sample-btn').addEventListener('click', async () => {{
  const msg = document.getElementById('sample-msg');
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
const fallback = document.getElementById('fallback');
const video = document.getElementById('demo-video');
function showFallback() {{
  video.style.display = 'none';
  fallback.classList.add('on');
}}
video.addEventListener('error', showFallback, true);
fetch('/watch/demo/video', {{method: 'HEAD'}}).then(r => {{
  if (!r.ok) showFallback();
}}).catch(showFallback);
async function buy(btn, payload) {{
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
  try {{
    const r = await fetch('/api/orders', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{amount: payload.amount, currency: 'USD',
                            description: payload.description}})
    }});
    const data = await r.json();
    if (r.ok && data.approve_url) {{
      window.location = data.approve_url;
      return;
    }}
    throw new Error(data.detail || 'real checkout unavailable');
  }} catch (err) {{
    try {{
      const r2 = await fetch('/api/watch/demo/checkout', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{amount: payload.amount,
                              description: payload.description}})
      }});
      const mock = await r2.json();
      if (!r2.ok) throw new Error(mock.detail || 'demo checkout failed');
      confirm.innerHTML = '<h3>Demo checkout complete</h3>'
        + '<p><b>' + mock.description + '</b> — $' + mock.amount + '</p>'
        + '<p>Mock order: ' + mock.order_id + '</p>'
        + '<p><b>This was a mock checkout. No real PayPal payment was '
        + 'made or charged.</b></p>';
      confirm.className = 'confirm';
      confirm.style.display = 'block';
    }} catch (err2) {{
      msg.innerHTML = '<span class="err">Checkout failed: '
        + err2.message + '</span>';
    }}
  }} finally {{
    btn.disabled = false;
    btn.textContent = 'Buy';
  }}
}}
</script>
"""
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>In-video shopping demo · {html.escape(brand)}</title>"
        f"<style>{_CSS}</style></head><body>{body}"
        f"<footer>{html.escape(brand)} — turn any video into a checkout page.</footer>"
        "</body></html>"
    )
