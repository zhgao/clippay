"""URL import for the video pipeline: turn a video *link* into a transcript.

This is the friction-killer for the "upload an mp4" entry point: creators'
videos live on YouTube / TikTok / Instagram, not on disk, so asking them
to download and re-upload is a redundant step. Import follows the same
three-tier idea already proven in the sibling Transcriptly project:

  1. YouTube captions first (no download, most reliable).
  2. Otherwise download with yt-dlp and transcribe the audio.
  3. Anything that fails surfaces as a clear UrlImportError — never a
     crash, never a silent empty product list.

Reliability, stated honestly
----------------------------
YouTube captions are the stable path (no download involved). TikTok and
Instagram go through the download path, which is best-effort: those
platforms may block automated downloads, and this module must never
promise 100% success for them. The landing page copy says so in plain
language, and every failure mode below returns a readable error.

Testability
-----------
Everything external is injectable: the caption fetcher and the audio
downloader are constructor arguments, and `import_from_url` takes the
transcriber as a parameter. Tests inject fakes and never touch the
network, yt-dlp, or caption APIs.
"""
import glob
import os
import re
import subprocess
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from .transcribe import Transcriber


class UrlImportError(Exception):
    """A readable URL-import failure, with the HTTP status it maps to."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def invalid_url(message: str) -> UrlImportError:
    """400-class error: the caller's input is wrong, not the platform."""
    return UrlImportError(message, status=400)


def upstream_failure(message: str) -> UrlImportError:
    """502-class error: the platform (or a helper tool) failed us."""
    return UrlImportError(message, status=502)


_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "vm.tiktok.com"}
_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}


def detect_platform(url: str) -> str | None:
    """Return 'youtube', 'tiktok', 'instagram', or None when unsupported.

    Returns None for non-http(s) URLs, missing hosts, and hosts outside
    the three supported platforms — the endpoint turns that into a 400.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    if host in _YOUTUBE_HOSTS:
        return "youtube"
    if host in _TIKTOK_HOSTS:
        return "tiktok"
    if host in _INSTAGRAM_HOSTS:
        return "instagram"
    return None


def extract_youtube_video_id(url: str) -> str | None:
    """Extract the video id from watch / youtu.be / shorts / embed URLs."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "youtu.be":
        video_id = parts.path.strip("/").split("/")[0]
        return video_id or None
    if "youtube.com" in host:
        query = parse_qs(parts.query)
        if query.get("v"):
            return query["v"][0]
        match = re.match(r"^/(shorts|embed|live)/([^/?#]+)", parts.path)
        if match:
            return match.group(2)
    return None


class CaptionFetcher(Protocol):
    def fetch_transcript(self, url: str) -> list[dict]:
        """Return timestamped segments for a video URL."""
        ...


class YouTubeCaptionFetcher:
    """YouTube captions via youtube-transcript-api (lazy import).

    The library's API changed across versions: newer releases expose an
    instance ``fetch(video_id)`` returning snippet objects, older ones a
    static ``get_transcript(video_id)`` returning dicts. Both spellings
    and both entry shapes are handled. ``api`` is injectable for tests:
    pass any object with a ``fetch`` or ``get_transcript`` method and no
    real package is needed.
    """

    def __init__(self, api=None):
        self._api = api

    def _load_api(self):
        if self._api is not None:
            return self._api
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError as exc:
            raise upstream_failure(
                "youtube-transcript-api is not installed. Install it with "
                "`pip install youtube-transcript-api` to enable the "
                "YouTube captions path."
            ) from exc
        try:
            return YouTubeTranscriptApi()
        except TypeError:
            return YouTubeTranscriptApi

    @staticmethod
    def _entry_fields(entry):
        if isinstance(entry, dict):
            return (
                entry.get("text", ""),
                entry.get("start", 0.0),
                entry.get("duration", 0.0),
            )
        return (
            getattr(entry, "text", ""),
            getattr(entry, "start", 0.0),
            getattr(entry, "duration", 0.0),
        )

    def fetch_transcript(self, url: str) -> list[dict]:
        video_id = extract_youtube_video_id(url)
        if not video_id:
            raise invalid_url(
                "could not find a YouTube video id in this URL — "
                "use a watch, youtu.be, shorts, or embed link"
            )
        api = self._load_api()
        try:
            if hasattr(api, "fetch"):
                entries = api.fetch(video_id)
            elif hasattr(api, "get_transcript"):
                entries = api.get_transcript(video_id)
            else:
                raise upstream_failure(
                    "unsupported youtube-transcript-api version: "
                    "neither fetch nor get_transcript is available"
                )
        except UrlImportError:
            raise
        except Exception as exc:
            raise upstream_failure(
                "could not fetch YouTube captions for this video "
                "(it may have captions disabled): "
                f"{exc}"
            ) from exc
        segments = []
        for entry in entries:
            text, start, duration = self._entry_fields(entry)
            text = (text or "").strip()
            if text:
                segments.append(
                    {
                        "start": float(start),
                        "end": float(start) + float(duration),
                        "text": text,
                    }
                )
        if not segments:
            raise upstream_failure(
                "YouTube returned no caption text for this video"
            )
        return segments


class AudioDownloader(Protocol):
    def download_audio(self, url: str, dest_dir: str) -> str:
        """Download a video's audio track; return the local file path."""
        ...


class YtDlpDownloader:
    """yt-dlp audio downloader (subprocess; binary must be installed)."""

    def download_audio(self, url: str, dest_dir: str) -> str:
        os.makedirs(dest_dir, exist_ok=True)
        template = os.path.join(dest_dir, "%(id)s.%(ext)s")
        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "-x",
                    "--audio-format",
                    "wav",
                    "--audio-quality",
                    "0",
                    "--no-playlist",
                    "-o",
                    template,
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except FileNotFoundError as exc:
            raise upstream_failure(
                "yt-dlp is not installed. Install it with "
                "`pip install yt-dlp` to enable the download path."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise upstream_failure(
                "download timed out after 300 seconds"
            ) from exc
        if result.returncode != 0:
            detail = (result.stderr or "").strip().splitlines()
            hint = detail[-1] if detail else "unknown yt-dlp error"
            raise upstream_failure(
                "could not download this video "
                f"(yt-dlp failed: {hint})"
            )
        candidates = sorted(glob.glob(os.path.join(dest_dir, "*.wav")))
        if not candidates:
            raise upstream_failure(
                "yt-dlp finished but produced no audio file"
            )
        return candidates[-1]


class UrlImporter:
    """Best-effort URL -> transcript import.

    YouTube tries captions first and falls back to download; TikTok and
    Instagram go straight to download. Every failure is a UrlImportError
    with a readable message — the endpoint maps it to an HTTP error and
    never creates a half-empty job from it.
    """

    def __init__(
        self,
        caption_fetcher: CaptionFetcher | None = None,
        downloader: AudioDownloader | None = None,
    ):
        self.caption_fetcher = caption_fetcher or YouTubeCaptionFetcher()
        self.downloader = downloader or YtDlpDownloader()

    def import_from_url(
        self, url: str, transcriber: Transcriber, work_dir: str
    ) -> dict:
        """Return {"segments", "source", "platform", "audio_path"}.

        source is "captions" (YouTube captions path, audio_path None) or
        "download" (yt-dlp + transcription, audio_path set). Raises
        UrlImportError on any failure.
        """
        url = (url or "").strip()
        platform = detect_platform(url)
        if platform is None:
            raise invalid_url(
                "unsupported video link — paste a YouTube, TikTok, or "
                "Instagram video URL (http/https)"
            )
        if platform == "youtube":
            try:
                segments = self.caption_fetcher.fetch_transcript(url)
                return {
                    "segments": segments,
                    "source": "captions",
                    "platform": platform,
                    "audio_path": None,
                }
            except UrlImportError as exc:
                # A 400 here means the URL itself is malformed for
                # captions (e.g. no video id) — do not mask it as a
                # download failure; only fall back on upstream errors.
                if exc.status == 400:
                    raise
                caption_error = str(exc)
            # Fall through to the download path with the caption error
            # kept for the final message if download also fails.
        else:
            caption_error = None
        try:
            audio_path = self.downloader.download_audio(url, work_dir)
            segments = transcriber.transcribe(audio_path)
        except UrlImportError as exc:
            # YouTube double failure: keep both reasons, so the caller
            # knows captions failed AND why the download did not save it.
            if caption_error:
                raise upstream_failure(
                    f"{exc} (captions also failed: {caption_error})"
                ) from exc
            raise
        except Exception as exc:
            raise upstream_failure(
                "could not import this video"
                + (
                    f" (captions also failed: {caption_error})"
                    if caption_error
                    else ""
                )
                + f": {exc}"
            ) from exc
        if not segments:
            raise upstream_failure(
                "no transcript could be produced for this video"
                + (
                    f" (captions also failed: {caption_error})"
                    if caption_error
                    else ""
                )
            )
        return {
            "segments": segments,
            "source": "download",
            "platform": platform,
            "audio_path": audio_path,
        }
