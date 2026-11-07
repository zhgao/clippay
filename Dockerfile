FROM python:3.12-slim

WORKDIR /app

# ffmpeg is needed by yt-dlp for audio extraction (link import) and by
# the demo-video generation script; faster-whisper decodes via PyAV.
# curl + unzip install Deno, the JS runtime yt-dlp uses to solve
# YouTube's JS verification challenges. 2026-11-07: from-url was blocked
# by YouTube on the Fly datacenter IP; Deno + the android/mweb player
# client is the $0 bypass attempt (no cookies, no paid proxy).
# DENO_INSTALL=/usr/local puts `deno` on PATH for yt-dlp to find.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl unzip ca-certificates \
    && curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV DATABASE_PATH=/data/clippay.db
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
