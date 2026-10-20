"""Minimal PayPal Orders API v2 client (sandbox by default).

Works with placeholder credentials: a clear PayPalError is raised only when
an actual API call is attempted without credentials configured. Tests inject
an httpx.MockTransport-backed client so no network or real credentials are
needed.
"""
import base64
import os
import time
from urllib.parse import quote, urlsplit

import httpx


class PayPalError(Exception):
    """Raised for PayPal API failures and missing configuration."""


def _sanitized_proxy_url() -> str | None:
    """Rebuild the proxy URL from env with percent-encoded credentials.

    Some sandboxed environments export a proxy URL whose rotating password
    contains characters that httpx's strict URL parser rejects. Re-encoding
    just the userinfo keeps the proxy usable. Returns None when no proxy
    env var is set (direct connection).
    """
    raw = (
        os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
    )
    if not raw:
        return None
    parts = urlsplit(raw)
    userinfo = ""
    if parts.username:
        userinfo = (
            quote(parts.username, safe="")
            + ":"
            + quote(parts.password or "", safe="")
            + "@"
        )
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{userinfo}{parts.hostname or ''}{port}"


class PayPalClient:
    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        webhook_id: str = "",
        base_url: str = "https://api-m.sandbox.paypal.com",
        http: httpx.Client | None = None,
        proxy: str | None = None,
        verify: str | bool = True,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.webhook_id = webhook_id
        self.base_url = base_url.rstrip("/")
        if http is not None:
            self.http = http
        else:
            # trust_env=False: we sanitize the proxy URL ourselves above;
            # letting httpx parse the raw env var can crash on special chars.
            # verify: path to a CA bundle when the egress proxy MITMs TLS
            # (e.g. /etc/ssl/certs/ca-certificates.crt in this sandbox).
            self.http = httpx.Client(
                timeout=30.0,
                trust_env=False,
                proxy=proxy if proxy is not None else _sanitized_proxy_url(),
                verify=verify,
            )
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # -- internal helpers -------------------------------------------------
    def _require_credentials(self) -> None:
        if not self.client_id or not self.client_secret:
            raise PayPalError(
                "PayPal credentials are not configured. Set PAYPAL_CLIENT_ID "
                "and PAYPAL_CLIENT_SECRET (and PAYPAL_WEBHOOK_ID for webhooks) "
                "from a PayPal Developer sandbox app."
            )

    def _check(self, response: httpx.Response) -> dict:
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise PayPalError(f"PayPal API error {response.status_code}: {detail}")
        return response.json()

    # -- auth -------------------------------------------------------------
    def get_access_token(self) -> str:
        """Return a cached OAuth2 access token, refreshing it when expired."""
        self._require_credentials()
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        basic = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        response = self.http.post(
            f"{self.base_url}/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
        data = self._check(response)
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    def _authed_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
        }

    # -- orders -----------------------------------------------------------
    def create_order(
        self,
        amount: str,
        currency: str = "USD",
        description: str | None = None,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict:
        """Create a PayPal order with CAPTURE intent.

        Returns the raw order payload, including ``id`` and ``links``
        (the buyer approval URL is the link with rel == "approve").
        """
        purchase_unit: dict = {
            "amount": {"currency_code": currency, "value": amount},
        }
        if description:
            purchase_unit["description"] = description
        body: dict = {"intent": "CAPTURE", "purchase_units": [purchase_unit]}
        if return_url or cancel_url:
            body["application_context"] = {
                "return_url": return_url or "",
                "cancel_url": cancel_url or "",
            }
        response = self.http.post(
            f"{self.base_url}/v2/checkout/orders",
            headers=self._authed_headers(),
            json=body,
        )
        return self._check(response)

    def capture_order(self, order_id: str) -> dict:
        """Capture payment for an approved order."""
        response = self.http.post(
            f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
            headers=self._authed_headers(),
            json={},
        )
        return self._check(response)

    @staticmethod
    def approval_url(order: dict) -> str | None:
        for link in order.get("links", []):
            if link.get("rel") == "approve":
                return link.get("href")
        return None

    # -- webhooks ---------------------------------------------------------
    def verify_webhook_signature(
        self,
        transmission_id: str,
        transmission_time: str,
        cert_url: str,
        auth_algo: str,
        transmission_sig: str,
        webhook_event: dict,
    ) -> bool:
        """Verify a webhook payload via PayPal's verify-webhook-signature API."""
        self._require_credentials()
        if not self.webhook_id:
            raise PayPalError(
                "PAYPAL_WEBHOOK_ID is not configured; cannot verify webhooks."
            )
        body = {
            "transmission_id": transmission_id,
            "transmission_time": transmission_time,
            "cert_url": cert_url,
            "auth_algo": auth_algo,
            "transmission_sig": transmission_sig,
            "webhook_id": self.webhook_id,
            "webhook_event": webhook_event,
        }
        response = self.http.post(
            f"{self.base_url}/v1/notifications/verify-webhook-signature",
            headers=self._authed_headers(),
            json=body,
        )
        return self._check(response).get("verification_status") == "SUCCESS"
