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

# --- M2: video pipeline -------------------------------------------------
# Directory where uploaded videos are stored.
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./data/uploads")
# faster-whisper model size (tiny/base/small/...). "tiny" keeps the demo
# fast on CPU; the model is downloaded lazily on first transcription.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "tiny")
# Gemini API key for product extraction. NOT required at boot: without a
# key, extraction degrades gracefully to an empty product list (the video
# pipeline still completes with just the transcript).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Default model: gemini-2.5-flash was retired for new users in Oct 2026
# (API returns 404). gemini-3.5-flash-lite verified working on a sibling
# Gemini path (4.4s, $0.00); override with GEMINI_MODEL when deploying.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
# Extraction call timeout (seconds). A real extraction was observed to take
# ~111s, so the old 60s default cut genuine calls short. Override with
# GEMINI_TIMEOUT when deploying.
try:
    GEMINI_TIMEOUT = float(os.environ.get("GEMINI_TIMEOUT", "180"))
except ValueError:
    GEMINI_TIMEOUT = 180.0
