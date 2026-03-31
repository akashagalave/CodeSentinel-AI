# 🔍 CodeSentinel AI

### Production-Grade Multi-Agent AI Code Review Platform

![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-7%20Microservices-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-EKS-232F3E?style=for-the-badge&logo=amazon-aws&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-FF6B35?style=for-the-badge)
![GPT-4o](https://img.shields.io/badge/GPT--4o-Agents-412991?style=for-the-badge&logo=openai&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-HPA-326CE5?style=for-the-badge&logo=kubernetes&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-Monitoring-E6522C?style=for-the-badge&logo=prometheus&logoColor=white)
![DVC](https://img.shields.io/badge/DVC-RAG%20Pipeline-945DD6?style=for-the-badge)

---

## 📖 Overview

**CodeSentinel AI** is a **production-grade, multi-agent GenAI platform** that automatically reviews GitHub Pull Requests — detecting security vulnerabilities, bugs, and performance issues before they reach production.

When a developer opens a PR → CodeSentinel responds in **620ms** (webhook) and posts a complete AI review within ~30 seconds — including OWASP category, CWE ID, confidence score, and fix suggestion.

---

## ❌ Problem

- Human reviewers take **2–4 hours** per PR at scale
- Static linters miss **context-dependent bugs** — null dereference, race conditions, logic errors
- Security issues (SQL injection, OWASP Top 10) slip through without semantic understanding
- No awareness of existing codebase patterns

---

## ✅ Solution

| Problem | Solution |
|---|---|
| Slow review | Automated review in ~30s |
| Missing context | RAG over 17,666 indexed functions |
| Security gaps | Semgrep OWASP + GPT-4o reasoning |
| Inconsistent quality | Structured JSON findings with confidence |
| Scale | EKS + per-service HPA |

---

## 🏗️ High-Level Architecture

```mermaid
flowchart TD
    GH[GitHub PR Opened]

    subgraph Gateway[:8000]
        HMAC[HMAC Verify]
        DIFF[Fetch PR Diff]
        BG[BackgroundTask]
    end

    subgraph Orchestrator[:8001 LangGraph]
        R[Node 1: Retrieve Context]
        P[Node 2: Parallel Review]
        A[Node 3: Aggregate]
        POST[Node 4: Post Review]
    end

    subgraph Agents
        BH[Bug Hunter :8003 GPT-4o]
        SS[Security Scanner :8004 Semgrep + GPT-4o]
        PA[Perf Advisor :8005 GPT-4o-mini]
    end

    subgraph Retrieval[:8002]
        DENSE[all-MiniLM-L6-v2]
        BM25[BM25 Sparse]
        RRF[RRF Fusion]
        CE[CrossEncoder Rerank]
    end

    GH --> HMAC --> DIFF --> BG
    BG --> R
    R --> DENSE & BM25 --> RRF --> CE
    CE --> P
    P --> BH & SS & PA
    BH & SS & PA --> A --> POST
    POST --> GC[GitHub Client :8006 PR Comment + Check-run]
```

---

## 🔁 End-to-End Request Flow

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant GH as GitHub
    participant GW as Gateway :8000
    participant OR as Orchestrator :8001
    participant RT as Retrieval :8002
    participant BH as Bug Hunter :8003
    participant SS as Security :8004
    participant PA as Perf :8005
    participant GC as GitHub Client :8006

    Dev->>GH: Opens Pull Request
    GH->>GW: POST /webhook/github
    GW->>GW: Verify HMAC-SHA256
    GW->>GH: Fetch PR diff async
    GW-->>GH: 200 OK in 620ms
    GW->>OR: BackgroundTask POST /review

    OR->>RT: POST /search
    RT->>RT: Dense + BM25 + RRF + CrossEncoder
    RT-->>OR: Top-5 similar functions

    par asyncio.gather
        OR->>BH: POST /review
        BH-->>OR: Bug findings
    and
        OR->>SS: POST /review
        SS->>SS: Semgrep OWASP scan
        SS-->>OR: Security findings
    and
        OR->>PA: POST /review
        PA-->>OR: Perf findings
    end

    OR->>OR: Deduplicate + Sort CRITICAL to LOW
    OR->>GC: POST /post-review
    GC->>GH: PR Comment + Check-run
    GH-->>Dev: Review notification
```

---

## 🧠 RAG Pipeline — 4 Stage DVC

```mermaid
flowchart LR
    subgraph S1[Stage 1: Ingestion]
        GHA[GitHub API 10 repos]
        FILES[2053 py files 518845 lines]
        GHA --> FILES
    end

    subgraph S2[Stage 2: AST Parsing]
        TREE[Tree-sitter AST]
        FUNC[17666 functions]
        FILES --> TREE --> FUNC
    end

    subgraph S3[Stage 3: Indexing]
        EMBED[all-MiniLM-L6-v2]
        CHROMA[ChromaDB 179MB]
        BM25I[BM25 Index 12MB]
        MLFLOW[MLflow DagsHub]
        FUNC --> EMBED --> CHROMA
        FUNC --> BM25I
        CHROMA & BM25I --> MLFLOW
    end

    subgraph S4[Stage 4: Evaluation]
        RAGAS[RAGAS Quality Gate faithfulness >= 0.81]
        GATE{Pass?}
        DEPLOY[Promote Index]
        BLOCK[Block CI/CD sys.exit 1]
        RAGAS --> GATE
        GATE -->|Yes| DEPLOY
        GATE -->|No| BLOCK
    end

    S1 --> S2 --> S3 --> S4
```

---

## 🔍 Hybrid Search Pipeline

```mermaid
flowchart TD
    Q[Query: PR Diff]

    subgraph Dense[Dense Retrieval]
        EMB[Embed query all-MiniLM-L6-v2]
        CQUERY[ChromaDB cosine similarity top 20]
        EMB --> CQUERY
    end

    subgraph Sparse[Sparse Retrieval]
        TOK[Tokenize underscore-aware]
        BQUERY[BM25 scores top 20]
        TOK --> BQUERY
    end

    subgraph Fusion[RRF Fusion]
        RRF[Reciprocal Rank Fusion k=60 60pct BM25]
        TOP20[Combined top 20]
        RRF --> TOP20
    end

    subgraph Rerank[CrossEncoder Rerank]
        CE[ms-marco-MiniLM sees query+doc together]
        TOP5[Final top 5]
        CE --> TOP5
    end

    Q --> EMB
    Q --> TOK
    CQUERY --> RRF
    BQUERY --> RRF
    TOP20 --> CE
    TOP5 --> ORCHESTRATOR[Orchestrator]
```

---

## 📊 Production Results

### SQL Injection Detected — Live Test

```
Input:
  def login(user, pwd):
      query = f"SELECT * FROM users WHERE user={user}"
      return db.execute(query)

Output:
  total_findings:  1
  critical_count:  1
  has_critical:    True
  total_cost_usd:  $0.0037
  latency_ms:      17,402ms

Finding:
  severity:     CRITICAL
  file:         src/db.py (lines 2-2)
  issue:        SQL injection via string formatting
  fix:          cursor.execute('SELECT * FROM users WHERE user = ?', (user,))
  owasp:        A03:2021 - Injection
  cwe:          CWE-89
  confidence:   95%
```

### Load Test — Locust on EKS + ALB

```
Endpoint:    POST /webhook/github
Users:       10 concurrent
Requests:    577
Failures:    0%
P95:         620ms
Average:     537ms
```

### RAG Quality — RAGAS

```
Functions indexed:    17,666
RAGAS faithfulness:   0.950   target >= 0.81
RAGAS precision:      0.920   target >= 0.76
Context recall:       0.880
Hybrid vs dense:      +21% recall
Cost per review:      $0.0037   93% under $0.06 budget
```

---

## 🖥️ Production Screenshots

### Grafana — Live Production Dashboard (EKS)
> Webhooks/sec, latency, service health, memory usag

![Grafana](docs/images/Grafana.png)


### FastAPI Docs — Gateway on AWS ALB
> Live OpenAPI served from EKS LoadBalancer

![FastAPI](docs/images/FastAPI.png)

### SQL Injection Detection — Terminal Output
> CRITICAL: OWASP A03:2021, CWE-89, 95% confidence

![SQL](docs/images/SQL.png)



---

## ⚡ Infrastructure

```mermaid
flowchart TB
    subgraph AWS
        subgraph EKS[EKS Cluster 3x t3.xlarge]
            subgraph NS[codesentinel]
                GW2[Gateway min:2 max:6]
                ORC[Orchestrator min:2 max:6]
                RET[Retrieval 4Gi min:1 max:3]
                BHH[Bug Hunter min:2 max:8]
                SCN[Security Scanner min:2 max:6]
                PFA[Perf Advisor min:2 max:4]
                GCL[GitHub Client replicas:1]
            end
            subgraph MON[monitoring]
                PROM2[Prometheus]
                GRAF[Grafana 16 panels]
            end
        end
        ALB[AWS ALB LoadBalancer]
        ECR[ECR 7 repositories]
        S3[S3 DVC artifacts]
        EBS[EBS Volume ChromaDB + BM25]
    end

    ALB --> GW2
    ECR --> RET & BHH & SCN & PFA & GW2 & ORC & GCL
    S3 --> RET
    RET --> EBS
    PROM2 --> GRAF
```


---

## 🧰 Tech Stack

| Category | Technology |
|---|---|
| Agent Orchestration | LangGraph StateGraph |
| Embeddings | all-MiniLM-L6-v2 |
| Vector DB | ChromaDB 1.5.5 |
| Keyword Search | BM25 rank-bm25 |
| Reranking | CrossEncoder ms-marco-MiniLM |
| LLM Bugs + Security | GPT-4o |
| LLM Perf | GPT-4o-mini |
| Security Scanner | Semgrep OWASP rules |
| LLM Tracing | Langfuse |
| RAG Quality | RAGAS |
| Data Pipeline | DVC 4-stage |
| Model Registry | MLflow + DagsHub |
| Serving | FastAPI async |
| Infrastructure | AWS EKS + ALB + EBS |
| Monitoring | Prometheus + Grafana |
| Load Testing | Locust |

---


---

## 🚀 Local Setup

```bash
git clone https://github.com/akashagalave/CodeSentinel-AI
cd CodeSentinel-AI

cp .env.example .env
# Add: OPENAI_API_KEY, GITHUB_TOKEN, LANGFUSE keys

# Pull pre-built index (skip 2hr pipeline)
dvc pull

# Start all 7 services
docker-compose up

# Health check
curl http://localhost:8000/health
curl http://localhost:8002/health  # docs_count: 17666

# Load test
locust -f locustfile.py --host http://localhost:8000 \
  --users 10 --spawn-rate 2 --run-time 2m --headless
```

---

## 👨‍💻 Author

**Akash Agalave** 








