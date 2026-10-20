"""Product extraction tests: Gemini HTTP is mocked via httpx.MockTransport;
no API key or network is needed."""
import json

import httpx
import pytest

from app.extract import ExtractionError, ProductExtractor, parse_products

SEGMENTS = [
    {"start": 12.5, "end": 20.0, "text": "This handmade mug is twenty dollars."},
]


def _gemini_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _gemini_reply(payload_text: str):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(":generateContent")
        assert request.headers["x-goog-api-key"] == "test-key"
        body = json.loads(request.content)
        prompt = body["contents"][0]["parts"][0]["text"]
        assert "handmade mug" in prompt
        assert "[12.5]" in prompt
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": payload_text}]}}
                ]
            },
        )

    return handler


def test_extract_products_happy_path():
    payload = json.dumps(
        [
            {
                "name": "Handmade Mug",
                "description": "A handmade ceramic mug.",
                "price": 20,
                "timestamp_seconds": 12.5,
            }
        ]
    )
    extractor = ProductExtractor(
        api_key="test-key", http=_gemini_client(_gemini_reply(payload))
    )
    products = extractor.extract_products(SEGMENTS)
    assert products == [
        {
            "name": "Handmade Mug",
            "description": "A handmade ceramic mug.",
            "price": "20.00",
            "timestamp_seconds": 12.5,
        }
    ]


def test_extract_products_missing_key_degrades_to_empty():
    # No key -> graceful degradation: empty list, no exception, so the
    # pipeline can still finish with just the transcript.
    extractor = ProductExtractor(api_key="")
    assert extractor.extract_products(SEGMENTS) == []


def test_extract_products_http_error():
    def handler(request):
        return httpx.Response(403, text="forbidden")

    extractor = ProductExtractor(
        api_key="test-key", http=_gemini_client(handler)
    )
    with pytest.raises(ExtractionError, match="Gemini API error 403"):
        extractor.extract_products(SEGMENTS)


def test_extract_products_unexpected_shape():
    def handler(request):
        return httpx.Response(200, json={"nope": True})

    extractor = ProductExtractor(
        api_key="test-key", http=_gemini_client(handler)
    )
    with pytest.raises(ExtractionError, match="Unexpected Gemini response"):
        extractor.extract_products(SEGMENTS)


# -- parse_products: defensive parsing ------------------------------------

def test_parse_strips_code_fences():
    raw = '```json\n[{"name": "Mug", "price": 20, "timestamp_seconds": 3}]\n```'
    products = parse_products(raw)
    assert products[0]["name"] == "Mug"
    assert products[0]["price"] == "20.00"
    assert products[0]["timestamp_seconds"] == 3.0


def test_parse_unwraps_products_object():
    raw = json.dumps({"products": [{"name": "Board", "price": "45.5"}]})
    products = parse_products(raw)
    assert products == [
        {
            "name": "Board",
            "description": "",
            "price": "45.50",
            "timestamp_seconds": 0.0,
        }
    ]


def test_parse_drops_invalid_entries():
    raw = json.dumps(
        [
            {"name": "", "price": 10},               # no name -> dropped
            {"name": "Free Sticker", "price": 0},    # non-positive -> dropped
            {"name": "Mystery", "price": "soon"},    # bad price -> dropped
            "not-a-dict",                            # not a dict -> dropped
            {"name": "Mug", "price": "$1,299.9", "timestamp_seconds": -5},
        ]
    )
    products = parse_products(raw)
    assert products == [
        {
            "name": "Mug",
            "description": "",
            "price": "1299.90",
            "timestamp_seconds": 0.0,  # negative clamped to 0
        }
    ]


def test_parse_garbage_raises():
    with pytest.raises(ExtractionError, match="unparseable"):
        parse_products("I found no products, sorry!")


def test_parse_empty_list_ok():
    assert parse_products("[]") == []
