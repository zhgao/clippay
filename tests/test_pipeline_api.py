"""M2 pipeline API tests: upload -> fake transcription -> fake extraction ->
shoppable page + dashboard. Everything external is faked; no network."""
import os

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.extract import ExtractionError
from app.main import create_app
from app.transcribe import TranscriptionError
from tests.fakes import FakeExtractor, FakePayPal, FakeTranscriber


@pytest.fixture
def env(tmp_path):
    db = Database(":memory:")
    transcriber = FakeTranscriber()
    extractor = FakeExtractor()
    app = create_app(
        db=db,
        paypal=FakePayPal(),
        transcriber=transcriber,
        extractor=extractor,
        upload_dir=str(tmp_path / "uploads"),
    )
    return {
        "client": TestClient(app),
        "db": db,
        "transcriber": transcriber,
        "extractor": extractor,
        "upload_dir": tmp_path / "uploads",
    }


def _upload(client, name="demo.mp4", content=b"\x00\x00\x00\x18ftypmp42-fake"):
    return client.post(
        "/api/videos", files={"file": (name, content, "video/mp4")}
    )


def test_upload_runs_pipeline_to_ready(env):
    resp = _upload(env["client"])
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "ready"
    assert job["filename"] == "demo.mp4"
    assert [p["name"] for p in job["products"]] == [
        "Handmade Mug",
        "Walnut Cutting Board",
    ]
    # File actually stored under the upload dir with the job id.
    stored = env["upload_dir"] / f"{job['id']}.mp4"
    assert stored.exists() and stored.read_bytes().startswith(b"\x00\x00\x00\x18")
    # The transcriber got the stored path; the extractor got its segments.
    assert env["transcriber"].calls == [str(stored)]
    assert env["extractor"].seen_segments[1]["text"].startswith("This handmade")
    # And the job is retrievable.
    got = env["client"].get(f"/api/jobs/{job['id']}")
    assert got.status_code == 200
    assert got.json()["status"] == "ready"


def test_upload_rejects_non_mp4(env):
    resp = env["client"].post(
        "/api/videos", files={"file": ("notes.txt", b"hi", "text/plain")}
    )
    assert resp.status_code == 400
    assert env["db"].list_jobs() == []


def test_get_job_404(env):
    assert env["client"].get("/api/jobs/nope").status_code == 404
    assert env["client"].get("/p/nope").status_code == 404


def test_transcription_failure_marks_job_failed(tmp_path):
    db = Database(":memory:")
    app = create_app(
        db=db,
        paypal=FakePayPal(),
        transcriber=FakeTranscriber(
            fail_with=TranscriptionError("faster-whisper is not installed")
        ),
        extractor=FakeExtractor(),
        upload_dir=str(tmp_path),
    )
    client = TestClient(app)
    resp = _upload(client)
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "failed"
    assert "faster-whisper" in job["error"]
    # The product page of a failed job explains instead of crashing.
    page = client.get(f"/p/{job['id']}")
    assert page.status_code == 200
    assert "not ready" in page.text


def test_extraction_failure_marks_job_failed(tmp_path):
    db = Database(":memory:")
    app = create_app(
        db=db,
        paypal=FakePayPal(),
        transcriber=FakeTranscriber(),
        extractor=FakeExtractor(
            fail_with=ExtractionError("GEMINI_API_KEY is not configured")
        ),
        upload_dir=str(tmp_path),
    )
    client = TestClient(app)
    job = _upload(client).json()
    assert job["status"] == "failed"
    assert "GEMINI_API_KEY" in job["error"]
    # Segments were still recorded before extraction failed.
    assert len(job["segments"]) == 3


def test_product_page_lists_products_with_checkout(env):
    job = _upload(env["client"]).json()
    page = env["client"].get(f"/p/{job['id']}")
    assert page.status_code == 200
    assert "Handmade Mug" in page.text
    assert "$20.00" in page.text
    assert "0:12" in page.text  # 12.5s formatted as m:ss
    assert "Walnut Cutting Board" in page.text
    assert "$45.00" in page.text
    assert "/api/orders" in page.text  # checkout wired to the M1 flow


def test_product_page_escapes_html(tmp_path):
    db = Database(":memory:")
    evil = [
        {
            "name": "<script>alert(1)</script>",
            "description": "x",
            "price": "1.00",
            "timestamp_seconds": 0.0,
        }
    ]
    app = create_app(
        db=db,
        paypal=FakePayPal(),
        transcriber=FakeTranscriber(),
        extractor=FakeExtractor(products=evil),
        upload_dir=str(tmp_path),
    )
    client = TestClient(app)
    job = _upload(client).json()
    page = client.get(f"/p/{job['id']}")
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;" in page.text


def test_dashboard_lists_jobs_and_orders(env):
    job = _upload(env["client"]).json()
    # Create an order through the M1 flow so the dashboard has both kinds.
    env["client"].post(
        "/api/orders",
        json={"amount": "20.00", "currency": "USD",
              "description": "Handmade Mug"},
    )
    page = env["client"].get("/dashboard")
    assert page.status_code == 200
    assert "demo.mp4" in page.text
    assert "ready" in page.text
    assert "ORDER-123" in page.text
    assert "Handmade Mug" in page.text
    assert job["id"] in page.text


def test_landing_page_has_upload_form(env):
    page = env["client"].get("/")
    assert page.status_code == 200
    assert "/api/videos" in page.text
    assert 'type="file"' in page.text
