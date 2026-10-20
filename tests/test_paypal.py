"""Unit tests for the PayPal client. All PayPal HTTP traffic is mocked."""
import httpx
import pytest

from app.paypal import PayPalClient, PayPalError

TOKEN_BODY = {"access_token": "test-token", "token_type": "Bearer", "expires_in": 3600}
ORDER_BODY = {
    "id": "ORDER-123",
    "status": "CREATED",
    "links": [
        {"rel": "self", "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/ORDER-123"},
        {"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-123"},
    ],
}


def client_for(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    return PayPalClient(
        client_id="cid",
        client_secret="csec",
        webhook_id="wh-1",
        http=httpx.Client(transport=transport),
        **kwargs,
    )


def test_access_token_is_cached():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=TOKEN_BODY)

    client = client_for(handler)
    assert client.get_access_token() == "test-token"
    assert client.get_access_token() == "test-token"
    assert calls["n"] == 1


def test_create_order_posts_expected_body():
    seen = {}

    def handler(request):
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json=TOKEN_BODY)
        seen["body"] = request.read().decode()
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(201, json=ORDER_BODY)

    client = client_for(handler)
    order = client.create_order("19.99", currency="USD", description="Clip video")
    assert order["id"] == "ORDER-123"
    assert (
        PayPalClient.approval_url(order)
        == "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-123"
    )
    import json as _json

    body = _json.loads(seen["body"])
    assert body["intent"] == "CAPTURE"
    assert body["purchase_units"][0]["amount"] == {
        "currency_code": "USD",
        "value": "19.99",
    }


def test_capture_order():
    def handler(request):
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json=TOKEN_BODY)
        assert request.url.path.endswith("/v2/checkout/orders/ORDER-123/capture")
        return httpx.Response(201, json={"id": "ORDER-123", "status": "COMPLETED"})

    client = client_for(handler)
    result = client.capture_order("ORDER-123")
    assert result["status"] == "COMPLETED"


def test_verify_webhook_signature_success_and_failure():
    def ok_handler(request):
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json=TOKEN_BODY)
        return httpx.Response(200, json={"verification_status": "SUCCESS"})

    def bad_handler(request):
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json=TOKEN_BODY)
        return httpx.Response(200, json={"verification_status": "FAILURE"})

    event = {"event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "ORDER-123"}}
    kwargs = dict(
        transmission_id="t1",
        transmission_time="2026-01-01T00:00:00Z",
        cert_url="https://example.com/cert",
        auth_algo="SHA256withRSA",
        transmission_sig="sig",
        webhook_event=event,
    )
    assert client_for(ok_handler).verify_webhook_signature(**kwargs) is True
    assert client_for(bad_handler).verify_webhook_signature(**kwargs) is False


def test_missing_credentials_raise_clear_error():
    client = PayPalClient()  # placeholders, no credentials
    with pytest.raises(PayPalError, match="not configured"):
        client.get_access_token()


def test_api_error_raises_paypal_error():
    def handler(request):
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json=TOKEN_BODY)
        return httpx.Response(
            422, json={"name": "UNPROCESSABLE_ENTITY", "message": "bad amount"}
        )

    client = client_for(handler)
    with pytest.raises(PayPalError, match="422"):
        client.create_order("abc")
