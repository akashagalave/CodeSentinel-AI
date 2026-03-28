# services/gateway/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/gateway/app/ ./services/gateway/app/
COPY shared/ ./shared/

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "services.gateway.app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
