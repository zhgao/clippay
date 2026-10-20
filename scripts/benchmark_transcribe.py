#!/usr/bin/env python
"""Real-transcription benchmark for the M2 pipeline (risk check #1).

Runs the app's own FasterWhisperTranscriber against real media files and
reports, per file: media duration, wall-clock transcription time and the
real-time factor (transcribe_time / media_duration; < 1.0 = faster than
real time). Model loading is timed separately because the first ever run
also downloads the model (~75 MB for "tiny") into the local HF cache.

Usage:
    .venv/bin/python scripts/benchmark_transcribe.py [MODEL_SIZE] FILE...

MODEL_SIZE defaults to the app config value (WHISPER_MODEL, "tiny").
Not part of the pytest suite: it needs the model download and real CPU.
"""
import subprocess
import sys
import time

sys.path.insert(0, ".")  # run from the repo root

from app import config  # noqa: E402
from app.transcribe import FasterWhisperTranscriber  # noqa: E402


def media_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def main() -> int:
    args = sys.argv[1:]
    model_size = config.WHISPER_MODEL
    if args and not args[0].endswith((".mp4", ".wav", ".flac", ".mp3")):
        model_size = args.pop(0)
    if not args:
        print(__doc__)
        return 2

    transcriber = FasterWhisperTranscriber(model_size=model_size)
    t0 = time.perf_counter()
    transcriber._load_model()
    load_secs = time.perf_counter() - t0
    print(f"model={model_size} load_time={load_secs:.2f}s "
          f"(includes download on first run)")

    for path in args:
        duration = media_duration(path)
        t0 = time.perf_counter()
        segments = transcriber.transcribe(path)
        elapsed = time.perf_counter() - t0
        rtf = elapsed / duration if duration else float("nan")
        print(f"\n{path}")
        print(f"  media_duration={duration:.2f}s transcribe_time={elapsed:.2f}s "
              f"rtf={rtf:.3f} segments={len(segments)}")
        for seg in segments[:3]:
            print(f"    [{seg['start']:.1f}-{seg['end']:.1f}] {seg['text'][:80]}")
        if len(segments) > 3:
            print(f"    ... and {len(segments) - 3} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
