"""Speech-to-text for the video pipeline.

A `Transcriber` turns a media file into timestamped segments:
``[{"start": 0.0, "end": 2.5, "text": "..."}, ...]``.

The production implementation uses faster-whisper, imported lazily inside
the `transcribe()` call so the app (and the test suite) runs fine without
the package installed and never downloads a model until a real video is
transcribed. Tests inject a fake transcriber instead.
"""
from typing import Protocol


class TranscriptionError(Exception):
    """Raised when transcription cannot be performed."""


class Transcriber(Protocol):
    def transcribe(self, media_path: str) -> list[dict]:
        """Return timestamped transcript segments for the media file."""
        ...


class FasterWhisperTranscriber:
    """faster-whisper-backed transcriber (model loaded lazily, CPU int8)."""

    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriptionError(
                "faster-whisper is not installed. Install it with "
                "`pip install faster-whisper` to enable transcription."
            ) from exc
        if self._model is None:
            self._model = WhisperModel(
                self.model_size, device="cpu", compute_type="int8"
            )
        return self._model

    def transcribe(self, media_path: str) -> list[dict]:
        model = self._load_model()
        segments, _info = model.transcribe(media_path)
        return [
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
            }
            for seg in segments
            if seg.text and seg.text.strip()
        ]


def get_transcriber(model_size: str = "tiny") -> Transcriber:
    """Factory for the default transcriber (used when none is injected)."""
    return FasterWhisperTranscriber(model_size=model_size)
