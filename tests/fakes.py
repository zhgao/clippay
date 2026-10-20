"""Shared test fakes."""


class FakePayPal:
    """Drop-in fake for PayPalClient used by the API layer."""

    def __init__(self, verify_result=True, fail_with: Exception | None = None):
        self.verify_result = verify_result
        self.fail_with = fail_with

    def _maybe_fail(self):
        if self.fail_with:
            raise self.fail_with

    def create_order(self, **kwargs):
        self._maybe_fail()
        return {
            "id": "ORDER-123",
            "status": "CREATED",
            "links": [
                {
                    "rel": "approve",
                    "href": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-123",
                }
            ],
        }

    def capture_order(self, order_id):
        self._maybe_fail()
        return {
            "id": "ORDER-123",
            "status": "COMPLETED",
            "payer": {"email_address": "buyer@example.com"},
        }

    def verify_webhook_signature(self, **kwargs):
        self._maybe_fail()
        return self.verify_result


FAKE_SEGMENTS = [
    {"start": 0.0, "end": 4.0, "text": "Welcome to my workshop tour."},
    {"start": 12.5, "end": 20.0, "text": "This handmade mug is twenty dollars."},
    {"start": 40.0, "end": 48.0, "text": "And the walnut cutting board is $45."},
]

FAKE_PRODUCTS = [
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


class FakeTranscriber:
    """Returns canned segments; never touches faster-whisper or models."""

    def __init__(self, segments=None, fail_with: Exception | None = None):
        self.segments = FAKE_SEGMENTS if segments is None else segments
        self.fail_with = fail_with
        self.calls: list[str] = []

    def transcribe(self, media_path: str):
        self.calls.append(media_path)
        if self.fail_with:
            raise self.fail_with
        return [dict(seg) for seg in self.segments]


class FakeExtractor:
    """Returns canned products; never calls Gemini."""

    def __init__(self, products=None, fail_with: Exception | None = None):
        self.products = FAKE_PRODUCTS if products is None else products
        self.fail_with = fail_with
        self.seen_segments = None

    def extract_products(self, segments):
        self.seen_segments = segments
        if self.fail_with:
            raise self.fail_with
        return [dict(p) for p in self.products]
