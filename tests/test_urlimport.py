"""Tests for URL import (POST /api/videos/from-url) and the one-click
sample (POST /api/videos/sample, GET /sample/{job_id}).

Everything external is faked: caption fetchers, downloaders, the
transcriber, and the extractor. No test touches the network, yt-dlp,
caption APIs, Gemini, or real PayPal credentials.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.extract import ExtractionError
from app.main import create_app
from app.urlimport import (
    UrlImportError,
    UrlImporter,
    YouTubeCaptionFetcher,
    detect_platform,
    extract_youtube_video_id,
)
from tests.fakes import FakeExtractor, FakePayPal, FakeTranscriber

CAPTION_SEGMENTS = [
    {"start": 0.0, "end": 5.0, "text": "Welcome to my workshop tour."},
    {"start": 5.0, "end": 12.0, "text": "This handmade mug is twenty dollars."},
]


class FakeCaptionFetcher:
    def __init__(self, segments=None, fail_with=None):
        self.segments = CAPTION_SEGMENTS if segments is None else segments
        self.fail_with = fail_with
        self.calls = []

    def fetch_transcript(self, url):
        self.calls.append(url)
        if self.fail_with:
            raise self.fail_with
        return [dict(s) for s in self.segments]


class FakeDownloader:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with
        self.calls = []

    def download_audio(self, url, dest_dir):
        self.calls.append((url, dest_dir))
        if self.fail_with:
            raise self.fail_with
        return os.path.join(dest_dir, "fake-audio.wav")


@pytest.fixture
def client_factory(tmp_path):
    def _make(caption=None, downloader=None, extractor=None,
              sample_media=None):
        importer = UrlImporter(
            caption_fetcher=caption or FakeCaptionFetcher(),
            downloader=downloader or FakeDownloader(),
        )
        media = sample_media
        if media is None:
            media = tmp_path / "pitch.mp4"
            media.write_bytes(b"fake-sample")
            media = str(media)
        app = create_app(
            db=Database(":memory:"),
            paypal=FakePayPal(),
            transcriber=FakeTranscriber(),
            extractor=extractor or FakeExtractor(),
            upload_dir=str(tmp_path / "uploads"),
            url_importer=importer,
            sample_media_path=media,
        )
        return TestClient(app), importer

    return _make


# -- platform detection ---------------------------------------------------


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abc123", "youtube"),
    ("https://youtube.com/watch?v=abc123", "youtube"),
    ("https://youtu.be/abc123", "youtube"),
    ("https://www.youtube.com/shorts/abc123", "youtube"),
    ("https://music.youtube.com/watch?v=abc123", "youtube"),
    ("https://www.tiktok.com/@user/video/123", "tiktok"),
    ("https://vm.tiktok.com/xyz", "tiktok"),
    ("https://www.instagram.com/reel/abc/", "instagram"),
    ("https://vimeo.com/12345", None),
    ("https://example.com/video.mp4", None),
    ("not a url", None),
    ("ftp://youtube.com/watch?v=abc", None),
    ("", None),
])
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abc123&t=5s", "abc123"),
    ("https://youtu.be/abc123", "abc123"),
    ("https://www.youtube.com/shorts/abc123", "abc123"),
    ("https://www.youtube.com/embed/abc123", "abc123"),
    ("https://www.youtube.com/live/abc123", "abc123"),
    ("https://www.youtube.com/playlist?list=xyz", None),
    ("https://www.youtube.com/watch", None),
])
def test_extract_youtube_video_id(url, expected):
    assert extract_youtube_video_id(url) == expected


# -- YouTube caption fetcher (stub API, both spellings/shapes) -----------


class StubFetchApi:
    def __init__(self, entries):
        self.entries = entries

    def fetch(self, video_id):
        assert video_id == "abc123"
        return self.entries


class StubOldApi:
    def __init__(self, entries):
        self.entries = entries

    def get_transcript(self, video_id):
        assert video_id == "abc123"
        return self.entries


class Snippet:
    def __init__(self, text, start, duration):
        self.text = text
        self.start = start
        self.duration = duration


def test_caption_fetcher_new_api_dict_entries():
    fetcher = YouTubeCaptionFetcher(
        api=StubFetchApi(
            [
                {"text": "hello", "start": 1.0, "duration": 2.0},
                {"text": "  ", "start": 3.0, "duration": 1.0},
            ]
        )
    )
    segments = fetcher.fetch_transcript("https://youtu.be/abc123")
    assert segments == [{"start": 1.0, "end": 3.0, "text": "hello"}]


def test_caption_fetcher_old_api():
    fetcher = YouTubeCaptionFetcher(
        api=StubOldApi([{"text": "hi", "start": 0.0, "duration": 1.5}])
    )
    segments = fetcher.fetch_transcript(
        "https://www.youtube.com/watch?v=abc123"
    )
    assert segments == [{"start": 0.0, "end": 1.5, "text": "hi"}]


def test_caption_fetcher_snippet_objects():
    fetcher = YouTubeCaptionFetcher(
        api=StubFetchApi([Snippet("hey", 2.0, 3.0)])
    )
    segments = fetcher.fetch_transcript("https://youtu.be/abc123")
    assert segments == [{"start": 2.0, "end": 5.0, "text": "hey"}]


def test_caption_fetcher_no_video_id_is_400():
    fetcher = YouTubeCaptionFetcher(api=StubFetchApi([]))
    with pytest.raises(UrlImportError) as exc_info:
        fetcher.fetch_transcript("https://www.youtube.com/playlist?list=x")
    assert exc_info.value.status == 400


def test_caption_fetcher_api_failure_is_502():
    class Boom:
        def fetch(self, video_id):
            raise RuntimeError("captions disabled")

    fetcher = YouTubeCaptionFetcher(api=Boom())
    with pytest.raises(UrlImportError) as exc_info:
        fetcher.fetch_transcript("https://youtu.be/abc123")
    assert exc_info.value.status == 502
    assert "captions" in str(exc_info.value)


# -- UrlImporter routing (real class, fake externals) ---------------------


def test_importer_youtube_uses_captions_not_download(tmp_path):
    caption = FakeCaptionFetcher()
    downloader = FakeDownloader()
    importer = UrlImporter(caption_fetcher=caption, downloader=downloader)
    result = importer.import_from_url(
        "https://www.youtube.com/watch?v=abc",
        FakeTranscriber(),
        str(tmp_path),
    )
    assert result["source"] == "captions"
    assert result["platform"] == "youtube"
    assert result["audio_path"] is None
    assert caption.calls == ["https://www.youtube.com/watch?v=abc"]
    assert downloader.calls == []


def test_importer_youtube_falls_back_to_download(tmp_path):
    caption = FakeCaptionFetcher(
        fail_with=UrlImportError("captions disabled", status=502)
    )
    downloader = FakeDownloader()
    transcriber = FakeTranscriber()
    importer = UrlImporter(caption_fetcher=caption, downloader=downloader)
    result = importer.import_from_url(
        "https://youtu.be/abc", transcriber, str(tmp_path)
    )
    assert result["source"] == "download"
    assert result["segments"] == FakeTranscriber().segments
    assert downloader.calls[0][0] == "https://youtu.be/abc"
    assert transcriber.calls == [os.path.join(str(tmp_path), "fake-audio.wav")]


def test_importer_youtube_caption_400_is_not_masked(tmp_path):
    caption = FakeCaptionFetcher(
        fail_with=UrlImportError("no video id", status=400)
    )
    downloader = FakeDownloader()
    importer = UrlImporter(caption_fetcher=caption, downloader=downloader)
    with pytest.raises(UrlImportError) as exc_info:
        importer.import_from_url(
            "https://youtu.be/abc", FakeTranscriber(), str(tmp_path)
        )
    assert exc_info.value.status == 400
    assert downloader.calls == []


def test_importer_tiktok_goes_straight_to_download(tmp_path):
    caption = FakeCaptionFetcher()
    downloader = FakeDownloader()
    importer = UrlImporter(caption_fetcher=caption, downloader=downloader)
    result = importer.import_from_url(
        "https://www.tiktok.com/@u/video/1", FakeTranscriber(), str(tmp_path)
    )
    assert result["source"] == "download"
    assert result["platform"] == "tiktok"
    assert caption.calls == []


def test_importer_rejects_bad_and_unsupported_urls(tmp_path):
    importer = UrlImporter(
        caption_fetcher=FakeCaptionFetcher(), downloader=FakeDownloader()
    )
    for bad in ("not a url", "", "https://vimeo.com/123"):
        with pytest.raises(UrlImportError) as exc_info:
            importer.import_from_url(bad, FakeTranscriber(), str(tmp_path))
        assert exc_info.value.status == 400


def test_importer_download_failure_is_502(tmp_path):
    importer = UrlImporter(
        caption_fetcher=FakeCaptionFetcher(),
        downloader=FakeDownloader(
            fail_with=UrlImportError("yt-dlp failed", status=502)
        ),
    )
    with pytest.raises(UrlImportError) as exc_info:
        importer.import_from_url(
            "https://www.instagram.com/reel/1",
            FakeTranscriber(),
            str(tmp_path),
        )
    assert exc_info.value.status == 502


# -- Endpoints ------------------------------------------------------------


def test_from_url_captions_path_returns_ready_job(client_factory):
    client, _ = client_factory()
    resp = client.post(
        "/api/videos/from-url",
        json={"url": "https://www.youtube.com/watch?v=abc"},
    )
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "ready"
    assert job["filename"] == "https://www.youtube.com/watch?v=abc"
    assert [p["name"] for p in job["products"]] == [
        "Handmade Mug",
        "Walnut Cutting Board",
    ]
    assert len(job["segments"]) == 2
    assert job["segments"][0]["text"].startswith("Welcome")


def test_from_url_download_fallback_returns_ready_job(client_factory):
    caption = FakeCaptionFetcher(
        fail_with=UrlImportError("captions disabled", status=502)
    )
    client, _ = client_factory(caption=caption)
    resp = client.post(
        "/api/videos/from-url",
        json={"url": "https://www.tiktok.com/@u/video/1"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "ready"


def test_from_url_invalid_url_is_400_and_creates_no_job(client_factory):
    client, _ = client_factory()
    resp = client.post("/api/videos/from-url", json={"url": "notaurl"})
    assert resp.status_code == 400
    assert "YouTube, TikTok" in resp.json()["detail"]
    resp = client.post(
        "/api/videos/from-url", json={"url": "https://vimeo.com/1"}
    )
    assert resp.status_code == 400
    assert client.get("/dashboard").status_code == 200
    assert "notaurl" not in client.get("/dashboard").text


def test_from_url_platform_failure_is_502_and_creates_no_job(client_factory):
    downloader = FakeDownloader(
        fail_with=UrlImportError("yt-dlp failed: ERROR", status=502)
    )
    client, _ = client_factory(downloader=downloader)
    resp = client.post(
        "/api/videos/from-url",
        json={"url": "https://www.instagram.com/reel/1"},
    )
    assert resp.status_code == 502
    assert "yt-dlp" in resp.json()["detail"]


def test_from_url_extraction_failure_marks_job_failed(client_factory):
    extractor = FakeExtractor(
        fail_with=ExtractionError("GEMINI_API_KEY is not configured")
    )
    client, _ = client_factory(extractor=extractor)
    resp = client.post(
        "/api/videos/from-url",
        json={"url": "https://www.youtube.com/watch?v=abc"},
    )
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "failed"
    assert "GEMINI_API_KEY" in job["error"]


def test_sample_endpoint_runs_pipeline_and_page_shows_flow(client_factory):
    client, _ = client_factory()
    resp = client.post("/api/videos/sample")
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "ready"
    assert [p["name"] for p in job["products"]] == [
        "Handmade Mug",
        "Walnut Cutting Board",
    ]
    page = client.get(f"/sample/{job['id']}")
    assert page.status_code == 200
    assert "Welcome to my workshop tour" in page.text
    assert "Handmade Mug" in page.text
    assert "/watch/demo" in page.text  # transcript -> products -> player
    assert "did not clearly state" in page.text  # tote honesty note


def test_sample_page_404(client_factory):
    client, _ = client_factory()
    assert client.get("/sample/nope").status_code == 404


def test_sample_endpoint_falls_back_without_media(client_factory):
    # Deployed servers have no bundled audio (binaries cannot go
    # through the text-only deploy path): the endpoint must still
    # return a ready job with the pre-computed transcript + products.
    client, _ = client_factory(sample_media="/nonexistent/pitch.mp4")
    resp = client.post("/api/videos/sample")
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "ready"
    assert [p["name"] for p in job["products"]] == [
        "Handmade Ceramic Mug",
        "Walnut Cutting Board",
        "Organic Cotton Tote Bag",
    ]
    assert [p["price"] for p in job["products"]] == ["20.00", "45.00", "12.00"]
    assert len(job["segments"]) == 1
    assert job["segments"][0]["text"].startswith("Welcome to my work shop")
    page = client.get(f"/sample/{job['id']}")
    assert page.status_code == 200
    assert "Handmade Ceramic Mug" in page.text
    assert "did not clearly state" in page.text  # tote honesty note
    assert "pre-computed" in page.text  # fallback honesty note


def test_landing_and_watch_pages_expose_new_entry_points(client_factory):
    client, _ = client_factory()
    landing = client.get("/")
    assert landing.status_code == 200
    assert "/api/videos/from-url" in landing.text
    assert "Try the demo instantly" in landing.text
    assert "best-effort" in landing.text
    watch = client.get("/watch/demo")
    assert watch.status_code == 200
    assert "Try the sample instantly" in watch.text
    assert "/api/videos/sample" in watch.text
