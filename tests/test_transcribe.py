"""Transcriber tests: factory laziness + the faster-whisper glue, exercised
through a fake `faster_whisper` module so no model is ever downloaded."""
import sys
import types

from app.transcribe import FasterWhisperTranscriber, TranscriptionError, get_transcriber


def test_factory_returns_lazy_transcriber():
    transcriber = get_transcriber("tiny")
    assert isinstance(transcriber, FasterWhisperTranscriber)
    # Construction must not load a model (lazy): nothing downloaded in tests.
    assert transcriber._model is None


def _install_fake_faster_whisper(monkeypatch):
    class FakeSegment:
        def __init__(self, start, end, text):
            self.start, self.end, self.text = start, end, text

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path):
            segments = [
                FakeSegment(0.0, 2.0, " hello "),
                FakeSegment(2.0, 4.5, "world"),
                FakeSegment(4.5, 5.0, "   "),  # blank -> dropped
            ]
            return segments, object()

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)


def test_whisper_transcribe_normalizes_segments(monkeypatch):
    _install_fake_faster_whisper(monkeypatch)
    transcriber = FasterWhisperTranscriber("tiny")
    segments = transcriber.transcribe("/tmp/whatever.mp4")
    assert segments == [
        {"start": 0.0, "end": 2.0, "text": "hello"},
        {"start": 2.0, "end": 4.5, "text": "world"},
    ]


def test_missing_package_raises_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    transcriber = FasterWhisperTranscriber("tiny")
    try:
        transcriber.transcribe("/tmp/whatever.mp4")
    except TranscriptionError as exc:
        assert "faster-whisper is not installed" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected TranscriptionError")
