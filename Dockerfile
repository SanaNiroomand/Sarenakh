# --- 1) build the React app -------------------------------------------------------------
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2) Python runtime serving API + SSE + static files ----------------------------------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/
COPY samples/ samples/
COPY --from=web /web/dist frontend/dist

# Non-root runtime user (Kubernetes runAsNonRoot); /app/data is the only writable path (SQLite).
ARG APP_UID=10001
RUN groupadd --system --gid ${APP_UID} app \
 && useradd --system --uid ${APP_UID} --gid ${APP_UID} --home-dir /app --no-create-home app \
 && mkdir -p /app/data && chown app:app /app/data
USER ${APP_UID}:${APP_UID}

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

# One worker on purpose: SQLite + in-process background runs + SSE fan-out live in one process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-keep-alive", "75"]
