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
→ topic-level theme inference
→ theme materialization
```

The original input remains the source of truth. PostgreSQL stores pipeline
state and generated classifications. Ollama has no direct database access.

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

## Topics and themes

Topics remain question-aware and fine-grained: they describe what one answer
or segment means in its question context. Themes are globally scoped,
inferred abstractions across complete topic membership. Theme inference does
not cluster raw answer embeddings. Instead, the worker aggregates all
completed original and segment inputs by case-insensitive topic, checks topic
eligibility, and presents one topic cluster at a time to the theme model.

The relationship is intentionally many-to-many:

```text
original_inputs.topic ─┐
                       ├→ theme_topics.topic → themes
segment_inputs.topic ──┘
```

A topic may belong to several themes, and a theme may contain several topics.

## Theme suggestions and live state

`theme_suggestions` and its evidence/link tables are an immutable audit trail
of model decisions. Materialization applies those decisions to live
`themes`/`theme_topics` state in the same transaction:

- `new` creates a theme, or effectively reuses a live case-insensitive name.
- `reuse` adds topic links without changing the theme description.
- `update` adds links and applies the proposed name and description.
- `merge` picks the lowest live root ID, moves topic links, applies the
  proposed name and description, and keeps losing rows as aliases.

Merged rows use `themes.merged_into_id`; they are not deleted because audit
records reference them. Alias paths are compressed so merged rows point
directly to a live root. Readers follow that pointer and deduplicate canonical
themes. Pending suggestions are replayed when the theme worker starts and at
the beginning of every cycle.

## Runtime services

Docker Compose starts PostgreSQL with pgvector, Ollama, a model initializer, a
database migration job, the FastAPI service, and one service for each worker.
The backend image is shared by the API and all worker processes.
