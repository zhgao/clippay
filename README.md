# ClipPay

**Turn any video into a shoppable checkout page.** An AI agent watches a video,
extracts the products mentioned in it, and generates a page where every item
can be bought with PayPal — creators monetize existing content with zero
store setup.

Entry for the **PayPal AI Hackathon 2026**
([official page](https://paypalaihackathon.devpost.com/)).

> Milestone M1 (this repo state): payment rails only — PayPal Orders API v2
> integration (create/capture), signature-verified webhooks, and a local
> SQLite order store. The video/AI pipeline lands in M2.

## How it works (M1)

```
POST /api/orders                  -> create a PayPal order (CAPTURE intent),
                                     returns the buyer approval URL
buyer approves in PayPal sandbox  -> PayPal calls POST /api/webhooks/paypal
POST /api/orders/{id}/capture     -> capture the approved order
GET  /api/orders/{id}             -> local order record
```

Webhook events handled: `CHECKOUT.ORDER.APPROVED` and
`PAYMENT.CAPTURE.COMPLETED`. Every webhook payload is verified with PayPal's
`verify-webhook-signature` API before being processed.

## Setup

Requirements: Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your sandbox credentials
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API docs.

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

## Environment variables

| Variable             | Required | Default                              | Description                                  |
|----------------------|----------|--------------------------------------|----------------------------------------------|
| `PAYPAL_CLIENT_ID`   | yes      | _(empty)_                             | Sandbox app client ID                        |
| `PAYPAL_CLIENT_SECRET` | yes    | _(empty)_                             | Sandbox app secret                           |
| `PAYPAL_WEBHOOK_ID`  | yes*     | _(empty)_                             | Webhook ID, for signature verification       |
| `PAYPAL_BASE_URL`    | no       | `https://api-m.sandbox.paypal.com`   | PayPal API base URL                          |
| `PAYPAL_CA_BUNDLE`  | no       | _(certifi default)_                   | CA bundle path, if your egress proxy MITMs TLS |
| `DATABASE_PATH`      | no       | `./data/clippay.db`                  | SQLite database file                         |
| `APP_BRAND_NAME`     | no       | `ClipPay`                            | Brand name shown in the PayPal checkout      |

\* Only needed for webhook verification. The app boots with placeholders;
a clear error is raised only when a PayPal call is attempted without
credentials.

## Tests

All PayPal HTTP traffic is mocked — no credentials or network needed:

```bash
pytest -v
```

## Roadmap

- **M1** ✅ Payment rails: Orders API, webhooks, order store (this milestone)
- **M2** Video upload → AI transcription → product extraction → shoppable page
- **M3** Polish, seller dashboard, hardening
- **M4** Demo video + Devpost submission

## License

MIT — see [LICENSE](LICENSE).
