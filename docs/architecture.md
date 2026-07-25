# Architecture

## Repository layout

```text
.
├── backend/
│   ├── src/triage_processor/
│   │   ├── api/
│   │   ├── clients/
│   │   ├── workers/
│   │   ├── config.py
│   │   └── job_queue.py
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
├── infrastructure/postgres/
├── docs/
└── compose.yaml
```

The frontend directory is intentionally empty until a UI stack is selected.
The backend is an independent Python project using a `src` package layout.
Deployment orchestration stays at the repository root, while database assets
live under `infrastructure`.

## Backend responsibilities

- `api` owns FastAPI application startup, HTTP schemas, and routes.
- `clients` owns communication with Ollama's chat and embedding APIs.
- `workers` owns the four executable pipeline consumers.
- `job_queue.py` owns durable job claiming, leases, retries, and completion.
- `config.py` owns shared environment-derived configuration.

## Processing flow

```text
HTTP input
→ eligibility and segmentation
→ embeddings
→ topic assignment
→ theme analysis
```

The original input remains the source of truth. PostgreSQL stores pipeline
state and generated classifications. Ollama has no direct database access.

## Runtime services

Docker Compose starts PostgreSQL with pgvector, Ollama, a model initializer, a
database migration job, the FastAPI service, and one service for each worker.
The backend image is shared by the API and all worker processes.
