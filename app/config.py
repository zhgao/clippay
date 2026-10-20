"""Application configuration loaded from environment variables.

PayPal sandbox credentials are NOT required at import/boot time: the app
starts fine with placeholders, and only raises a clear error when a PayPal
API call is actually attempted. Tests inject a mocked HTTP transport instead.
"""
import os

PAYPAL_BASE_URL = os.environ.get(
    "PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com"
)
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
PAYPAL_WEBHOOK_ID = os.environ.get("PAYPAL_WEBHOOK_ID", "")

DATABASE_PATH = os.environ.get("DATABASE_PATH", "./data/clippay.db")
APP_BRAND_NAME = os.environ.get("APP_BRAND_NAME", "ClipPay")
# Optional path to a CA bundle for TLS verification, e.g.
# /etc/ssl/certs/ca-certificates.crt when the egress proxy MITMs TLS.
PAYPAL_CA_BUNDLE = os.environ.get("PAYPAL_CA_BUNDLE", "")
