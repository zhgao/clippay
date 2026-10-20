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
