# 🔍 AI News Verification System

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Vector RAG](https://img.shields.io/badge/Vector_RAG-FastEmbed-818cf8.svg)](https://github.com/qdrant/fastembed)
[![Groq](https://img.shields.io/badge/Groq-LLM_Inference-f97316.svg)](https://groq.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An **LLM + RAG-based evidence verification system** that verifies news URLs and viral text claims against real-time reporting from global and regional news sources without relying on a traditional supervised fake-news classifier.

---

## 🎯 Core Product Objective

When encountering a suspicious claim on social media or browsing the web, users should not have to manually visit multiple news portals one by one. 

**VerifyNews** automates this multi-source investigation:
1. **Ingests** a news article URL or pasted text claim.
2. **Extracts** the core verifiable claim(s) and named entities using **Groq LLM**.
3. **Formulates** targeted search queries across multiple angles.
4. **Retrieves** real-time news articles from **NewsAPI** and **Google News (SerpAPI)**.
5. **Deduplicates** cross-publisher syndicated wire stories.
6. **Indexes & Semantically Searches** evidence using **FastEmbed (`BAAI/bge-small-en-v1.5`)** and in-memory cosine similarity search.
7. **Evaluates** stance (`SUPPORT`, `CONTRADICT`, `NEUTRAL`) and context for each retrieved source using Groq LLM.
8. **Synthesizes** a transparent verdict: `REAL`, `FALSE`, `MISLEADING`, or `UNVERIFIED` with evidence snippets and confidence breakdown.

---

## 🏗️ Architecture

```
USER INPUT (URL or Text)
       │
       ▼
 FastAPI Backend (/api/v1/verify)
       │
       ├─► [If URL] Article Extractor (newspaper3k + bs4)
       │
       ▼
 Groq LLM — Claim Extraction (Primary claim, Sub-claims, Entities)
       │
       ▼
 Groq LLM — Search Query Generation (3-5 targeted queries)
       │
       ├─────────────────────────┐
       ▼                         ▼
   NewsAPI Search         Google News (SerpAPI or RSS)
       │                         │
       └─────────────────────────┤
                                 ▼
                     Source Normalization & Wire Deduplication
                                 ▼
                      FastEmbed (384-dim Dense Vectors)
                                  ▼
                      In-Memory Semantic Vector Index
                                  ▼
                      Semantic Evidence Retrieval (Top-K)
                                 ▼
                     Groq LLM — Stance & Nuance Analysis (SUPPORT / CONTRADICT / NEUTRAL)
                                 ▼
                     Groq LLM — Final Verdict & Transparent Synthesis
                                 │
                                 ▼
                     REAL / FALSE / MISLEADING / UNVERIFIED
                                 │
                                 ▼
                     Interactive Single-Page UI
```

---

## 🏷️ Verdict Definitions

- **`REAL`**: Multiple authoritative retrieved sources independently confirm and support the central claim.
- **`FALSE`**: Authoritative retrieved evidence directly contradicts or refutes the central claim.
- **`MISLEADING`**: The claim contains partial truth but has missing context, exaggerates numbers, or presents outdated events as current.
- **`UNVERIFIED`**: Retrieved evidence is insufficient, inconclusive, or completely neutral.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.12
- Free [Groq API Key](https://console.groq.com)
- Free [NewsAPI Key](https://newsapi.org)
- (Optional) [SerpAPI Key](https://serpapi.com)

### 2. Installation
```bash
git clone https://github.com/jaiyan-th/AI-Powered-Fake-News-Detecter.git
cd AI-Powered-Fake-News-Detecter

# Install dependencies
python -m pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the project root:
```env
GROQ_API_KEY=your-groq-api-key
NEWS_API_KEY=your-news-api-key
SERPAPI_KEY=your-serpapi-key-optional
```

### 4. Start the Application
```bash
# Start FastAPI backend & UI
uvicorn backend.main:app --reload --port 8000
```

The Windows launcher is `START_HERE.bat`. On port conflicts, start Uvicorn with an available `--port`.

Open your browser at:
- **Interactive UI:** [http://localhost:8000](http://localhost:8000)
- **Swagger / OpenAPI Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **System Health Diagnostics:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

## Production deployment

VerifyNews serves the UI and API from the same FastAPI process. Run a single instance with one worker and a writable, persistent SQLite directory.

- Set `PRODUCTION=true` and keep `DEBUG=false`. Configure a stable `JWT_SECRET_KEY` generated with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Rotating that key signs users out.
- Set `GROQ_API_KEY` for claim and evidence analysis. Configure NewsAPI or SerpAPI keys if you use those providers.
- Put public deployments behind HTTPS and rate-limit verification and authentication requests at the proxy. The provided start commands also cap concurrent connections.
- Use `GET /api/v1/health` as the health check. A database failure returns HTTP 503. Provider configuration problems appear as degraded service information.
- The default frontend is same-origin. Set `CORS_ORIGINS` to a JSON list of permitted origins if you host a separate frontend.

### Docker Compose

Set the signing key and provider keys in `.env`, then run `docker compose up --build -d`. Compose binds to loopback for use behind a reverse proxy. It preserves SQLite data in the existing `./database` directory. On Linux, ensure the bind directory and any existing SQLite files are writable by container UID/GID `10001` before starting. Back up the database before changing storage or redeploying.

### Render

Use `render.yaml` for the build command, Uvicorn start command, and health check. For an existing manually configured service, use the same commands and set the environment values in the Render dashboard before deploying. To retain accounts and history across deploys, attach a persistent disk on a compatible plan, set `DATABASE_DIR` to its mount path, and restore any existing SQLite backup there before switching over. See [Render persistent disks](https://render.com/docs/disks).

---

## 📡 API Reference

### `POST /api/v1/verify`
Verify a news URL or text claim.

**Request Body:**
```json
{
  "url": "https://reuters.com/world/india/example-article",
  "text": null
}
```

**Response (200 OK):**
```json
{
  "verdict": "REAL",
  "confidence": 88,
  "confidence_label": "Verification Confidence",
  "claim": {
    "primary_claim": "India launched new solar energy initiative.",
    "secondary_claims": [],
    "entities": ["India", "Solar Mission"],
    "timeframe": "Recent"
  },
  "summary": "Multiple reputable sources confirm the government announcement.",
  "explanation": "Reuters and The Hindu both report that the cabinet approved the solar outlay today.",
  "evidence_summary": {
    "supporting": 2,
    "contradicting": 0,
    "neutral": 1,
    "total_sources_evaluated": 3
  },
  "sources": [
    {
      "source_name": "Reuters",
      "domain": "reuters.com",
      "title": "Cabinet Clears Solar Plan",
      "url": "https://reuters.com/...",
      "stance": "SUPPORT",
      "relevance_score": 0.94,
      "evidence_snippet": "The government approved the funding.",
      "credibility_tier": "WIRE_AND_PRIMARY_AGENCY"
    }
  ],
  "source_agreement_percentage": 100.0,
  "limitations": [
    "Analysis based on English-language articles available at query time."
  ],
  "pipeline_stages": [
    { "stage": "article_extraction", "status": "COMPLETED", "duration_ms": 350 },
    { "stage": "claim_extraction", "status": "COMPLETED", "duration_ms": 480 },
    { "stage": "multi_source_search", "status": "COMPLETED", "duration_ms": 1100 },
    { "stage": "semantic_vector_retrieval", "status": "COMPLETED", "duration_ms": 120 },
    { "stage": "verdict_synthesis", "status": "COMPLETED", "duration_ms": 650 }
  ],
  "processing_time_ms": 2700
}
```

---

## 🧪 Running Tests
```bash
python -m pip install -r requirements-dev.txt
python -m pytest backend/tests/ -v
```

---

## 📄 License
MIT License. Created for AI-powered news verification and claim investigation.
