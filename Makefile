# Makefile — developer shortcuts
# Usage: make <target>

.PHONY: up down build logs test load-test ingest deploy clean

# ── Local development ──────────────────────────────────────────
up:
	docker-compose up --build

down:
	docker-compose down

build:
	docker-compose build

logs:
	docker-compose logs -f

# ── Health checks ──────────────────────────────────────────────
health:
	@echo "Checking all services..."
	@curl -sf http://localhost:8000/health && echo " gateway    OK" || echo " gateway    FAIL"
	@curl -sf http://localhost:8001/health && echo " orchestrator OK" || echo " orchestrator FAIL"
	@curl -sf http://localhost:8002/health && echo " retrieval  OK" || echo " retrieval  FAIL"
	@curl -sf http://localhost:8003/health && echo " bug-hunter OK" || echo " bug-hunter FAIL"
	@curl -sf http://localhost:8004/health && echo " security   OK" || echo " security   FAIL"
	@curl -sf http://localhost:8005/health && echo " perf       OK" || echo " perf       FAIL"
	@curl -sf http://localhost:8006/health && echo " gh-client  OK" || echo " gh-client  FAIL"

# ── DVC pipeline ───────────────────────────────────────────────
ingest:
	cd ingestion-pipeline && dvc repro

ingest-push:
	dvc push

ingest-force:
	cd ingestion-pipeline && dvc repro --force

# ── Testing ────────────────────────────────────────────────────
test:
	pytest tests/ -v

load-test:
	locust -f locustfile.py --users 10 --spawn-rate 2 --run-time 2m --headless

# ── Test retrieval manually ────────────────────────────────────
test-search:
	curl -X POST http://localhost:8002/search \
	  -H "Content-Type: application/json" \
	  -d '{"query": "authenticate user with password", "k": 3}' | python -m json.tool

# ── K8s deploy ────────────────────────────────────────────────
k8s-deploy:
	kubectl apply -f infrastructure/kubernetes/namespace.yaml
	kubectl apply -f infrastructure/kubernetes/

k8s-status:
	kubectl get pods -n codesentinel
	kubectl get hpa -n codesentinel

k8s-logs:
	kubectl logs -n codesentinel -l app=$(svc) -f

# ── Clean ─────────────────────────────────────────────────────
clean:
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true