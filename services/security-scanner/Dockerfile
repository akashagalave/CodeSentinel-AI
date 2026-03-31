
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY services/security-scanner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/security-scanner/app/ ./services/security_scanner/app/
COPY shared/ ./shared/

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

EXPOSE 8004

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "services.security_scanner.app.main:app", \
     "--host", "0.0.0.0", "--port", "8004", "--workers", "2"]


