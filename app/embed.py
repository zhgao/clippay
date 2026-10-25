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

_CSS = """
body { font-family: system-ui, sans-serif; margin: 1rem auto; max-width: 720px;
       padding: 0 1rem; color: #1a1a2e; }
h1 { font-size: 1.25rem; }
.badge { display: inline-block; background: #fff3cd; border: 1px solid #e6c87a;
         border-radius: 999px; padding: .25rem .8rem; font-size: .85rem; }
.card { border: 1px solid #ddd; border-radius: 10px; padding: 1rem 1.25rem;
        margin: 1rem 0; }
.price { font-size: 1.25rem; font-weight: 700; }
.ts { color: #666; font-size: .85rem; }
.note { color: #666; font-size: .85rem; }
button { background: #0070ba; color: #fff; border: 0; border-radius: 6px;
         padding: .6rem 1.2rem; font-size: 1rem; cursor: pointer; }
button:disabled { opacity: .5; }
.confirm { border: 2px solid #2e7d32; border-radius: 10px; padding: 1rem 1.25rem;
           background: #f1f8f1; }
.err { color: #b00020; }
.brandline { color: #888; font-size: .8rem; margin-top: 2rem; }
"""


def _fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def embed_page(job: dict, brand: str, checkout_mode: str = "demo",
               has_video: bool = False) -> str:
    """Render the chromeless embeddable player for one ready job."""
    title = job.get("filename") or "Video"
    status = job.get("status", "")
    if checkout_mode == "sandbox":
        badge = "Sandbox checkout — PayPal Sandbox, no real money moves."
    else:
        badge = "Demo mode — mock checkout, no real payment is made."
    parts = [f"<h1>{html.escape(title)}</h1>", f'<p><span class="badge">{badge}</span></p>']
    if status != "ready":
        detail = html.escape(job.get("error") or f"status: {status}")
        parts.append(f'<p class="err">This player is not ready yet — {detail}</p>')
        body = "".join(parts)
        return _wrap(title, brand, body)

    if has_video:
        video_url = f"/api/jobs/{html.escape(job.get('id', ''))}/video"
        parts.append(
            f'<video controls playsinline preload="metadata" '
            f'style="width:100%" src="{video_url}"></video>'
        )
    products = job.get("products") or []
    if not products:
        parts.append("<p>No purchasable products were found in this video.</p>")
    has_tote = False
    for product in products:
        name = html.escape(product.get("name", ""))
        desc = html.escape(product.get("description", ""))
        price = html.escape(str(product.get("price", "")))
        ts = _fmt_ts(float(product.get("timestamp_seconds", 0)))
        if product.get("name") == "Organic Cotton Tote Bag":
            has_tote = True
        buy_arg = json.dumps(
            {"amount": str(product.get("price", "")), "description": product.get("name", "")}
        )
        buy_arg = (
            buy_arg.replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("'", "\\u0027")
        )
        parts.append(
            f'<div class="card"><h3>{name}</h3>'
            f"<p>{desc}</p>"
            f'<p class="price">${price}</p>'
            f'<p class="ts">Mentioned at {ts} in the video</p>'
            f"<button onclick='buy(this, {buy_arg})'>Buy with PayPal</button>"
            f"</div>"
        )
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
