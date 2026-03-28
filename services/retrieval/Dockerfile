# services/retrieval/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/retrieval/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/retrieval/app/ ./services/retrieval/app/
COPY shared/ ./shared/

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

EXPOSE 8002

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "services.retrieval.app.main:app", \
     "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]