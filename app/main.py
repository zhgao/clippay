"""ClipPay M1: payment rails.

Endpoints:
  GET  /healthz
  POST /api/orders                  create a PayPal order (CAPTURE intent)
  GET  /api/orders/{order_id}       local order record
  POST /api/orders/{order_id}/capture  capture an approved order
  POST /api/webhooks/paypal         PayPal webhook receiver (signature-verified)
"""
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import config
from .db import Database
from .paypal import PayPalClient, PayPalError


class CreateOrderRequest(BaseModel):
    amount: str = Field(..., description="Decimal amount, e.g. '19.99'")
    currency: str = "USD"
    description: str | None = None
    return_url: str | None = None
    cancel_url: str | None = None


class OrderResponse(BaseModel):
    order_id: str
    status: str
    approve_url: str | None
    amount: str
    currency: str


def create_app(
    db: Database | None = None,
    paypal: PayPalClient | None = None,
) -> FastAPI:
    db = db or Database(config.DATABASE_PATH)
    paypal = paypal or PayPalClient(
        client_id=config.PAYPAL_CLIENT_ID,
        client_secret=config.PAYPAL_CLIENT_SECRET,
        webhook_id=config.PAYPAL_WEBHOOK_ID,
        base_url=config.PAYPAL_BASE_URL,
        verify=config.PAYPAL_CA_BUNDLE or True,
    )

    app = FastAPI(title="ClipPay", version="0.1.0")

    def get_db() -> Database:
        return db

    def get_paypal() -> PayPalClient:
        return paypal

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "clippay"}

    @app.post("/api/orders", response_model=OrderResponse)
    def create_order(
        body: CreateOrderRequest,
        db: Database = Depends(get_db),
        paypal: PayPalClient = Depends(get_paypal),
    ):
        try:
            order = paypal.create_order(
                amount=body.amount,
                currency=body.currency,
                description=body.description,
                return_url=body.return_url,
                cancel_url=body.cancel_url,
            )
        except PayPalError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        record = db.upsert_order(
            paypal_order_id=order["id"],
            amount=body.amount,
            currency=body.currency,
            description=body.description,
            status=order.get("status", "CREATED"),
            raw=order,
        )
        return OrderResponse(
            order_id=order["id"],
            status=record["status"],
            approve_url=PayPalClient.approval_url(order),
            amount=record["amount"],
            currency=record["currency"],
        )

    @app.get("/api/orders/{order_id}")
    def get_order(order_id: str, db: Database = Depends(get_db)):
        record = db.get_order(order_id)
        if record is None:
            raise HTTPException(status_code=404, detail="order not found")
        return record

    @app.post("/api/orders/{order_id}/capture")
    def capture_order(
        order_id: str,
        db: Database = Depends(get_db),
        paypal: PayPalClient = Depends(get_paypal),
    ):
        try:
            result = paypal.capture_order(order_id)
        except PayPalError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        payer_email = (
            result.get("payer", {}).get("email_address")
            if isinstance(result.get("payer"), dict)
            else None
        )
        record = db.update_status(
            order_id, result.get("status", "COMPLETED"),
            payer_email=payer_email, raw=result,
        )
        return record or {"order_id": order_id, "status": result.get("status")}

    @app.post("/api/webhooks/paypal")
    async def paypal_webhook(
        request: Request,
        db: Database = Depends(get_db),
        paypal: PayPalClient = Depends(get_paypal),
        transmission_id: str = Header(default="", alias="paypal-transmission-id"),
        transmission_time: str = Header(default="", alias="paypal-transmission-time"),
        cert_url: str = Header(default="", alias="paypal-cert-url"),
        auth_algo: str = Header(default="", alias="paypal-auth-algo"),
        transmission_sig: str = Header(default="", alias="paypal-transmission-sig"),
    ):
        event = await request.json()
        try:
            verified = paypal.verify_webhook_signature(
                transmission_id=transmission_id,
                transmission_time=transmission_time,
                cert_url=cert_url,
                auth_algo=auth_algo,
                transmission_sig=transmission_sig,
                webhook_event=event,
            )
        except PayPalError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        if not verified:
            raise HTTPException(status_code=400, detail="invalid webhook signature")

        event_type = event.get("event_type", "")
        resource = event.get("resource", {}) or {}
        if event_type == "CHECKOUT.ORDER.APPROVED":
            db.update_status(resource.get("id", ""), "APPROVED", raw=event)
        elif event_type == "PAYMENT.CAPTURE.COMPLETED":
            order_id = (
                (resource.get("supplementary_data", {}) or {})
                .get("related_ids", {})
                .get("order_id", "")
            )
            payer_email = (
                (resource.get("payer", {}) or {}).get("email_address")
                if isinstance(resource.get("payer"), dict)
                else None
            )
            if order_id:
                db.update_status(order_id, "COMPLETED",
                                 payer_email=payer_email, raw=event)
        # Unknown event types are acknowledged but ignored.
        return {"received": True, "event_type": event_type}

    return app


app = create_app()
