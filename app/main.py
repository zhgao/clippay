"""ClipPay: payment rails (M1) + video -> shoppable page pipeline (M2).

Endpoints:
  GET  /                              landing page with the upload form
  GET  /healthz
  POST /api/orders                    create a PayPal order (CAPTURE intent)
  GET  /api/orders/{order_id}         local order record
  POST /api/orders/{order_id}/capture capture an approved order
  POST /api/webhooks/paypal           PayPal webhook receiver (verified)
  POST /api/videos                    upload an mp4 -> transcribe -> extract
  GET  /api/jobs/{job_id}             pipeline job record
  GET  /p/{job_id}                    shoppable page for a processed video
  GET  /dashboard                     seller dashboard (jobs + orders)
"""
import os
import uuid

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import config, pages
from .db import Database
from .extract import ExtractionError, ProductExtractor
from .paypal import PayPalClient, PayPalError
from .transcribe import FasterWhisperTranscriber, Transcriber, TranscriptionError


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
    transcriber: Transcriber | None = None,
    extractor: ProductExtractor | None = None,
    upload_dir: str | None = None,
) -> FastAPI:
    db = db or Database(config.DATABASE_PATH)
    paypal = paypal or PayPalClient(
        client_id=config.PAYPAL_CLIENT_ID,
        client_secret=config.PAYPAL_CLIENT_SECRET,
        webhook_id=config.PAYPAL_WEBHOOK_ID,
        base_url=config.PAYPAL_BASE_URL,
        verify=config.PAYPAL_CA_BUNDLE or True,
    )
    transcriber = transcriber or FasterWhisperTranscriber(
        model_size=config.WHISPER_MODEL
    )
    extractor = extractor or ProductExtractor(
        api_key=config.GEMINI_API_KEY,
        model=config.GEMINI_MODEL,
        verify=config.PAYPAL_CA_BUNDLE or True,
    )
    upload_dir = upload_dir or config.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    brand = config.APP_BRAND_NAME

    app = FastAPI(title="ClipPay", version="0.2.0")

    def get_db() -> Database:
        return db

    def get_paypal() -> PayPalClient:
        return paypal

    # -- basics -----------------------------------------------------------
    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "clippay"}

    @app.get("/", response_class=HTMLResponse)
    def landing():
        return pages.landing_page(brand)

    # -- M1: payment rails --------------------------------------------------
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

    # -- M2: video pipeline -------------------------------------------------
    def _process_job(job_id: str) -> dict:
        """Run transcription + extraction for an uploaded job.

        Synchronous by design (demo scale): the job record always ends in
        'ready' or 'failed' with a readable error, never stuck in between.
        """
        job = db.get_job(job_id)
        try:
            db.update_job(job_id, status="transcribing")
            segments = transcriber.transcribe(job["stored_path"])
            db.update_job(job_id, status="extracting", segments=segments)
            products = extractor.extract_products(segments)
            return db.update_job(job_id, status="ready", products=products)
        except (TranscriptionError, ExtractionError) as exc:
            return db.update_job(job_id, status="failed", error=str(exc))
        except Exception as exc:  # defensive: never leave a job hanging
            return db.update_job(
                job_id, status="failed",
                error=f"unexpected pipeline error: {exc}",
            )

    @app.post("/api/videos", status_code=201)
    async def upload_video(file: UploadFile = File(...)):
        filename = file.filename or ""
        if not filename.lower().endswith(".mp4"):
            raise HTTPException(
                status_code=400, detail="only .mp4 uploads are supported"
            )
        job_id = uuid.uuid4().hex[:12]
        stored_path = os.path.join(upload_dir, f"{job_id}.mp4")
        with open(stored_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
        db.create_job(job_id, filename, stored_path)
        return _process_job(job_id)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = db.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/p/{job_id}", response_class=HTMLResponse)
    def product_page(job_id: str):
        job = db.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="video not found")
        return pages.product_page(job, brand)

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard():
        return pages.dashboard_page(db.list_jobs(), db.list_orders(), brand)

    return app


app = create_app()
