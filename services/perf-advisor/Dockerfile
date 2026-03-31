
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/perf-advisor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/perf-advisor/app/ ./services/perf_advisor/app/
COPY shared/ ./shared/

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8005/health || exit 1

EXPOSE 8005

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "services.perf_advisor.app.main:app", \
     "--host", "0.0.0.0", "--port", "8005", "--workers", "2"]
