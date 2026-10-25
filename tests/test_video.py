"""Tests for job video serving (GET /api/jobs/{job_id}/video) and the
<video> element on the product and embed pages.

The route never accepts a caller-supplied path: it only serves the
stored_path recorded for a job, and only when that path resolves
inside the upload directory. Jobs without media (pre-computed sample,
captions-only imports) and paths escaping the directory all get 404.
No test here touches the network, Gemini, or real PayPal credentials.
"""
import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from tests.fakes import FAKE_PRODUCTS, FakePayPal

FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 1024


@pytest.fixture
def media_client(tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    media = upload_dir / "job123.mp4"
    media.write_bytes(FAKE_MP4)
    # A real file that lives OUTSIDE the upload dir: the route must
    # refuse it even though it exists (traversal / escape attempt).
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(FAKE_MP4)

    db = Database(":memory:")
    app = create_app(db=db, paypal=FakePayPal(), upload_dir=str(upload_dir))
    products = [dict(p) for p in FAKE_PRODUCTS]
    db.create_job("job123", "pitch.mp4", str(media))
    db.update_job("job123", status="ready", segments=[], products=products)
    # Pre-computed sample style: empty stored_path, no media file.
    db.create_job("jobempty", "pitch.mp4 (built-in sample, pre-computed)", "")
    db.update_job("jobempty", status="ready", segments=[], products=products)
    # Stored path inside the upload dir, but the file was never written.
    db.create_job("jobgone", "gone.mp4", str(upload_dir / "gone.mp4"))
    db.update_job("jobgone", status="ready", segments=[], products=products)
    # Absolute path escaping the upload dir.
    db.create_job("jobescape", "evil.mp4", str(outside))
    db.update_job("jobescape", status="ready", segments=[], products=products)
    # Relative path escaping the upload dir.
    db.create_job("jobdotdot", "evil2.mp4", "../outside.mp4")
    db.update_job("jobdotdot", status="ready", segments=[], products=products)
    return TestClient(app)


def test_video_route_serves_media(media_client):
    resp = media_client.get("/api/jobs/job123/video")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.content == FAKE_MP4


def test_video_route_range_returns_206(media_client):
    resp = media_client.get(
        "/api/jobs/job123/video", headers={"Range": "bytes=0-99"}
    )
    assert resp.status_code == 206
    assert resp.content == FAKE_MP4[:100]
    assert "content-range" in resp.headers
    assert resp.headers["content-range"].startswith("bytes 0-99/")


def test_video_route_unknown_job_404(media_client):
    assert media_client.get("/api/jobs/nope/video").status_code == 404


def test_video_route_no_media_job_404(media_client):
    assert media_client.get("/api/jobs/jobempty/video").status_code == 404


def test_video_route_missing_file_404(media_client):
    assert media_client.get("/api/jobs/jobgone/video").status_code == 404


def test_video_route_escapes_blocked(media_client):
    # Both escape shapes return 404 — the outside file exists, but the
    # route must never serve anything outside the upload directory.
    assert media_client.get("/api/jobs/jobescape/video").status_code == 404
    assert media_client.get("/api/jobs/jobdotdot/video").status_code == 404


def test_product_page_shows_video_when_media(media_client):
    html = media_client.get("/p/job123").text
    assert "<video" in html
    assert "/api/jobs/job123/video" in html
    assert "controls" in html
    assert "playsinline" in html
    assert 'preload="metadata"' in html


def test_product_page_no_video_element_without_media(media_client):
    html = media_client.get("/p/jobempty").text
    assert "<video" not in html
    # The page still works: products and the embed section are intact.
    assert "Handmade Mug" in html
    assert "Embed on your website" in html


def test_embed_page_shows_video_when_media(media_client):
    html = media_client.get("/embed/job123").text
    assert "<video" in html
    assert "/api/jobs/job123/video" in html
    assert "controls" in html
    assert "playsinline" in html


def test_embed_page_no_video_element_without_media(media_client):
    html = media_client.get("/embed/jobempty").text
    assert "<video" not in html
    assert "Handmade Mug" in html
