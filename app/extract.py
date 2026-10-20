"""Product extraction from transcripts via Gemini Flash.

Sends the timestamped transcript to Gemini and asks for a strict JSON list
of purchasable products. The response is parsed defensively: markdown code
fences are stripped, entries without a usable name or a positive price are
dropped, and numbers are coerced/clamped.

Graceful degradation: with no API key configured the extractor returns an
empty product list instead of raising, so the video pipeline still
completes (transcript + shoppable page work end to end; the page simply
shows no products). Genuine API/parse failures still raise
`ExtractionError`.
"""
import json
import re

import httpx

from .paypal import _sanitized_proxy_url

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"

PROMPT_TEMPLATE = """\
You are a commerce extraction agent. Below is a timestamped transcript of a
video. Identify every product that is mentioned as purchasable or offered
for sale (physical goods, digital products, services with a price).

Return ONLY a JSON array (no prose, no markdown) where each element is:
{{"name": "<short product name>",
  "description": "<one-sentence description>",
  "price": <suggested price in USD as a number>,
  "timestamp_seconds": <start time in seconds where the product is mentioned>}}

Rules:
- Use the timestamp of the segment where the product is first mentioned.
- If a price is stated in the video, use it; otherwise suggest a plausible
  retail price in USD.
- If no purchasable product is mentioned, return [].

Transcript (format: [start_seconds] text):
{transcript}
"""


class ExtractionError(Exception):
    """Raised for Gemini configuration or response failures."""


def _coerce_price(value) -> float | None:
    """Best-effort price coercion; None when unusable or non-positive."""
    if isinstance(value, (int, float)):
        price = float(value)
    elif isinstance(value, str):
        cleaned = value.strip().lstrip("$").replace(",", "")
        try:
            price = float(cleaned)
        except ValueError:
            return None
    else:
        return None
    return price if price > 0 else None


def _coerce_timestamp(value) -> float:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, ts)


def parse_products(raw_text: str) -> list[dict]:
    """Parse Gemini's reply text into validated product dicts.

    Defensive by design: tolerates ```json fences and a wrapping object
    ({"products": [...]}), drops malformed entries, and normalizes types.
    """
    text = (raw_text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ExtractionError(
            f"Gemini returned unparseable output: {raw_text[:200]!r}"
        ) from exc
    if isinstance(data, dict):
        data = data.get("products", [])
    if not isinstance(data, list):
        raise ExtractionError(
            f"Gemini returned unexpected JSON shape: {type(data).__name__}"
        )
    products = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        price = _coerce_price(
            item.get("price", item.get("suggested_price"))
        )
        if not name or price is None:
            continue
        products.append(
            {
                "name": name,
                "description": str(item.get("description") or "").strip(),
                "price": f"{price:.2f}",
                "timestamp_seconds": _coerce_timestamp(
                    item.get("timestamp_seconds", item.get("timestamp"))
                ),
            }
        )
    return products


class ProductExtractor:
    """Gemini Flash-backed product extractor."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-2.5-flash",
        http: httpx.Client | None = None,
        verify: str | bool = True,
    ):
        self.api_key = api_key
        self.model = model
        if http is not None:
            self.http = http
        else:
            # Same egress handling as the PayPal client: sanitize the proxy
            # env var ourselves (httpx can choke on special characters).
            self.http = httpx.Client(
                timeout=60.0,
                trust_env=False,
                proxy=_sanitized_proxy_url(),
                verify=verify,
            )

    def extract_products(self, segments: list[dict]) -> list[dict]:
        if not self.api_key:
            # Graceful degradation: no key -> no products, no failure.
            # The pipeline still finishes with the transcript stored.
            return []
        transcript = "\n".join(
            f"[{float(seg.get('start', 0)):.1f}] {seg.get('text', '')}"
            for seg in segments
        )
        prompt = PROMPT_TEMPLATE.format(transcript=transcript)
        response = self.http.post(
            f"{GEMINI_BASE_URL}/v1beta/models/{self.model}:generateContent",
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2,
                },
            },
        )
        if response.status_code >= 400:
            raise ExtractionError(
                f"Gemini API error {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
            parts = payload["candidates"][0]["content"]["parts"]
            raw_text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ExtractionError(
                f"Unexpected Gemini response shape: {str(payload)[:300]}"
            ) from exc
        return parse_products(raw_text)
