# AEGIS Fraud Detection Platform — Backend + 3 static portals
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    AEGIS_DATA_DIR=/data

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Backend code
COPY backend/app ./app

# Static portals (served by FastAPI)
COPY portals ./portals

# Migrations, models, training, scripts (kept in image for tooling)
COPY migrations ./migrations
COPY models ./models
COPY training ./training
COPY scripts ./scripts

# Data dir (SQLite + any file state) — mount a volume here
RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
