FROM python:3.12-slim

WORKDIR /app

# ffmpeg is needed by yt-dlp for audio extraction (link import) and by
# the demo-video generation script; faster-whisper decodes via PyAV.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV DATABASE_PATH=/data/clippay.db
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
