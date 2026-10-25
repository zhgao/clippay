"""One-click sample page (GET /sample/{job_id}).

After the "Try the demo instantly" button runs the built-in pitch
sample through the normal pipeline, this page shows the result in
order: transcript, then products, then a big button into the one-click
in-video player (/watch/demo) where checkout happens. It is a read-only
view over an ordinary pipeline job — no new pipeline code lives here.

Honesty notes (same as the watch page): the tote bag's $12.00 was
inferred during extraction, not clearly spoken in the audio, and this
page never claims otherwise. The sample uses the built-in pitch audio,
not a viewer's video.
"""
import html
import os

DEFAULT_SAMPLE_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), "..", "data", "samples", "pitch.mp4"
    )
)

_CSS = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 760px;
       padding: 0 1rem; color: #1a1a2e; }
h1 { font-size: 1.6rem; } h2 { margin-top: 2rem; }
.card { border: 1px solid #ddd; border-radius: 10px; padding: 1rem 1.25rem;
        margin: 1rem 0; }
.price { font-size: 1.25rem; font-weight: 700; }
.ts { color: #666; font-size: .85rem; }
.note { color: #666; font-size: .85rem; }
.seg { border-bottom: 1px solid #eee; padding: .4rem 0; }
button, .btn { background: #0070ba; color: #fff; border: 0; border-radius: 6px;
         padding: .6rem 1.2rem; font-size: 1rem; cursor: pointer;
         text-decoration: none; display: inline-block; }
.err { color: #b00020; }
footer { margin-top: 3rem; color: #888; font-size: .8rem; }
"""


def _fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def sample_page(job: dict, brand: str) -> str:
    title = job.get("filename") or "Sample video"
    status = job.get("status", "")
    parts = [f"<h1>{html.escape(brand)} — Sample demo</h1>"]
    parts.append(
        "<p>This is the built-in pitch sample — no upload needed. "
        "It ran through the same pipeline as any uploaded video: "
        "transcript, then products, then the one-click player.</p>"
    )
    if status != "ready":
        detail = html.escape(job.get("error") or f"status: {status}")
        parts.append(f'<p class="err">This sample is not ready yet — {detail}</p>')
        parts.append('<p><a href="/">Back to the demo</a></p>')
        return _page(title, brand, "".join(parts))

    parts.append("<h2>Transcript</h2>")
    segments = job.get("segments") or []
    if not segments:
        parts.append("<p>No transcript segments were produced.</p>")
    for seg in segments:
        text = html.escape(seg.get("text", ""))
        ts = _fmt_ts(float(seg.get("start", 0)))
        parts.append(f'<div class="seg"><span class="ts">[{ts}]</span> {text}</div>')

    parts.append("<h2>Products found</h2>")
    products = job.get("products") or []
    if not products:
        parts.append("<p>No purchasable products were found in this video.</p>")
    for product in products:
        name = html.escape(product.get("name", ""))
        desc = html.escape(product.get("description", ""))
        price = html.escape(str(product.get("price", "")))
        ts = _fmt_ts(float(product.get("timestamp_seconds", 0)))
        parts.append(
            f'<div class="card"><h3>{name}</h3>'
            f"<p>{desc}</p>"
            f'<p class="price">${price}</p>'
            f'<p class="ts">Mentioned at {ts} in the video</p>'
            f"</div>"
        )
    parts.append(
        '<p><a class="btn" href="/watch/demo">Watch &amp; buy in the '
        "one-click player →</a></p>"
    )
    parts.append(
        "<p class=\"note\">Note: the Organic Cotton Tote Bag's $12.00 was "
        "inferred during extraction — the audio did not clearly state "
        "that price, and this page does not claim the video spoke it. "
        "The player checkout is labelled mock when no PayPal Sandbox "
        "credentials are configured.</p>"
    )
    parts.append('<p><a href="/dashboard">Seller dashboard</a></p>')
    return _page(title, brand, "".join(parts))


def _page(title: str, brand: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)} · {html.escape(brand)}</title>"
        f"<style>{_CSS}</style></head><body>{body}"
        f"<footer>{html.escape(brand)} — turn any video into a checkout page.</footer>"
        "</body></html>"
    )
