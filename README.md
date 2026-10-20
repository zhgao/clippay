# ClipPay

**Turn any video into a shoppable checkout page.** An AI agent watches a video,
extracts the products mentioned in it, and generates a page where every item
can be bought with PayPal — creators monetize existing content with zero
store setup.

Entry for the **PayPal AI Hackathon 2026**
([official page](https://paypalaihackathon.devpost.com/)).

## How it works

```
seller uploads an .mp4        POST /api/videos
  -> faster-whisper transcribes it (timestamped segments)
  -> Gemini Flash extracts products (name, description, price, timestamp)
  -> a shoppable page is generated        GET /p/{job_id}
buyer clicks "Buy with PayPal"  POST /api/orders  -> PayPal sandbox approval
buyer approves in PayPal      -> PayPal calls POST /api/webhooks/paypal
seller captures the order     POST /api/orders/{id}/capture
seller watches it all         GET /dashboard (videos + orders)
```

The pipeline runs synchronously at upload time (demo scale): every job ends
in status `ready` or `failed` with a readable error — e.g. when
`GEMINI_API_KEY` is not configured or faster-whisper is not installed.

### Payments (M1)

- `POST /api/orders` creates a PayPal order (CAPTURE intent) and returns the
  buyer approval URL; `POST /api/orders/{id}/capture` captures it;
  `GET /api/orders/{id}` reads the local record.
- Webhook events handled: `CHECKOUT.ORDER.APPROVED` and
  `PAYMENT.CAPTURE.COMPLETED`. Every webhook payload is verified with PayPal's
  `verify-webhook-signature` API before being processed.

## Setup

Requirements: Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your credentials (see below)
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/ to upload a video, and
http://127.0.0.1:8000/docs for the interactive API docs.

### Getting PayPal sandbox credentials (free, ~5 minutes)

1. Sign in at <https://developer.paypal.com/> and go to
   **Apps & Credentials → Sandbox → Create App**.
2. Copy the **Client ID** and **Secret** into `.env` as
   `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET`.
3. Under the app's **Webhooks**, add a webhook subscribed to
   `CHECKOUT.ORDER.APPROVED` and `PAYMENT.CAPTURE.COMPLETED`,
   pointing at `https://<your-public-url>/api/webhooks/paypal`,
   then copy its **Webhook ID** into `PAYPAL_WEBHOOK_ID`.
   (For local development, expose the app with a tunnel such as ngrok.)

### Getting a Gemini API key (free)

1. Go to <https://aistudio.google.com/> → **Get API key** → create a key.
2. Put it in `.env` as `GEMINI_API_KEY`. Without it the app still boots and
   takes uploads; jobs fail at the extraction step with a clear error.

### Transcription

Transcription runs locally with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (installed via
`requirements.txt`). The model (`WHISPER_MODEL`, default `tiny`) is
downloaded lazily on the first transcription and runs on CPU — no GPU or
paid transcription API needed.

## Environment variables

| Variable               | Required | Default                              | Description                                  |
|------------------------|----------|--------------------------------------|----------------------------------------------|
| `PAYPAL_CLIENT_ID`     | yes      | _(empty)_                            | Sandbox app client ID                        |
| `PAYPAL_CLIENT_SECRET` | yes      | _(empty)_                            | Sandbox app secret                           |
| `PAYPAL_WEBHOOK_ID`    | yes*     | _(empty)_                            | Webhook ID, for signature verification       |
| `PAYPAL_BASE_URL`      | no       | `https://api-m.sandbox.paypal.com`   | PayPal API base URL                          |
| `PAYPAL_CA_BUNDLE`     | no       | _(certifi default)_                  | CA bundle path, if your egress proxy MITMs TLS |
| `DATABASE_PATH`        | no       | `./data/clippay.db`                  | SQLite database file                         |
| `APP_BRAND_NAME`       | no       | `ClipPay`                            | Brand name shown in pages and PayPal checkout |
| `GEMINI_API_KEY`       | yes†     | _(empty)_                            | Google AI Studio API key for extraction      |
| `GEMINI_MODEL`         | no       | `gemini-2.5-flash`                   | Gemini model for product extraction          |
| `UPLOAD_DIR`           | no       | `./data/uploads`                     | Where uploaded videos are stored             |
| `WHISPER_MODEL`        | no       | `tiny`                               | faster-whisper model size                    |

\* Only needed for webhook verification. † Only needed for the extraction
step. The app boots with placeholders; clear errors are raised only when a
feature is actually used without its configuration.

## Tests

Everything external is faked or mocked — no credentials, network, or model
downloads needed (the transcriber and Gemini are injected fakes;
faster-whisper itself is exercised through a stub module):

```bash
pytest -v
```

## Roadmap

- **M1** ✅ Payment rails: Orders API, webhooks, order store
- **M2** ✅ Video upload → transcription → product extraction → shoppable
  page → seller dashboard
- **M3** Polish, hardening, English copy pass
- **M4** Demo video + Devpost submission

## License

MIT — see [LICENSE](LICENSE).
