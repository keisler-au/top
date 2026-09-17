# Architecture

## Components

```text
frontend (framework-free Web Components)
    -> /api proxy -> FastAPI routes
        -> PostgreSQL + pgvector
        -> Ollama chat and embedding APIs
        -> evidence-preparation workers and batch taxonomy scheduler
        -> article-generation worker
```

`backend/` is a Python `src` project. `frontend/` is a framework-free
TypeScript/Web Components application. `infrastructure/postgres/` contains the
fresh-install schema and ordered migrations; `compose.yaml` connects runtime
services. The API owns HTTP validation, `clients/` owns model communication,
and workers own background processing.

## Backend responsibilities

- `api` owns FastAPI application startup, HTTP schemas, and routes.
- `clients` owns communication with Ollama's chat and embedding APIs.
- `workers` owns eligibility/segmentation, embeddings, and article generation.
- `job_queue.py` owns durable job claiming, leases, retries, and completion.
- `config.py` owns shared environment-derived configuration.

## Evidence preparation and batch taxonomy

```text
HTTP input
→ eligibility and segmentation
→ embeddings
→ immutable batch snapshot
→ leased clustering, topic naming, theme inference, reconciliation, and quality
→ one published taxonomy run
```

The original input remains the source of truth. PostgreSQL stores pipeline
state and generated classifications. Ollama has no direct database access.
The evidence queue has exactly two executable types: `eligibility_segmentation`
and `embeddings`. The batch scheduler owns all taxonomy stages in its separate
run-stage lease model.

## Question context

Question identity is normalized in `questions` as:

```text
(source, form_key, question_key, question_version)
```

Each row stores an immutable `question_text` snapshot. A new wording requires a
new positive `question_version`; neither an existing question nor an answer's
`question_id` can be mutated. `original_inputs.submission_key` groups the
answers from one submission, but is only meaningful together with the
question's source and form. Inputs without question context remain valid,
fully generic inputs.

Eligibility and topic assignment can use question text to interpret terse
answers such as “Price” or “No”. Segments still contain answer content only.
Embeddings contain `Question: …` and `Answer: …` for contextual inputs, while
generic inputs retain answer-only embeddings.

## Published taxonomy and legacy archive

```text
frozen canonical evidence -> embeddings -> clustering -> literal topics
    -> reconciled themes -> reviewed candidate run -> one published run
```

Every production reader resolves the one published run; article associations
retain stable taxonomy snapshots. The retired incremental topic/theme workers,
queue types, and reader fallbacks have no runtime path. Its historical
classifications, themes, suggestions, and assignment metadata are retained
only in the immutable `taxonomy_legacy_archive` audit schema. The mutable
legacy source tables and topic columns were destructively removed by migration
`037_drop_legacy_taxonomy_schema.sql`; the archive is their only retained
taxonomy history. See the active [current work packages](work-packages.md).
