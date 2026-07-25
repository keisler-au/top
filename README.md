This system stores original comments, embeds them for similarity search, asks a local LLM to suggest tags/themes/flags, and supports human review.

# Project Context

## Objective

Build a local system that captures user inputs, identifies distinct points within them, creates semantic embeddings, assigns topics, and identifies recurring themes across multiple inputs.

The original input remains the source of truth. LLM outputs are stored as system-generated classifications and suggestions.

## Core stack

* FastAPI for the application API
* PostgreSQL with pgvector for relational data and vector search
* Ollama for local LLM and embedding models
* Python workers for background processing

## Processing workflow

```text
Input received
→ saved unchanged in PostgreSQL
→ eligibility and segmentation
→ full-input and segment embeddings
→ similarity search
→ topic assignment
→ theme identification
```

## Worker responsibilities

### Worker 1: eligibility and segmentation

Processes new inputs.

* Determine whether the input is eligible.
* If eligible, split multi-topic inputs into meaningful segments.
* Preserve the original wording where possible.
* Save segments and mark the input ready for embedding.

### Worker 2: embeddings

Processes eligible inputs.

* Send the full input and its segments to the embedding model.
* Receive vectors from Ollama.
* Save vectors in PostgreSQL using pgvector.
* Mark the input ready for analysis.

The embedding model does not access the database directly.

### Worker 3: topic assignment

Processes embedded inputs.

* Find similar existing segments using pgvector.
* Retrieve relevant existing topics.
* Ask the LLM to reuse an existing topic or suggest a new one.
* Save topic assignments and mark the input complete.

### Worker 4: theme management

Runs periodically across completed inputs.

* Group related segments using embeddings and topics.
* Retrieve relevant existing themes.
* Ask the LLM to reuse, update, merge or create themes.
* Link themes to relevant topics and supporting inputs.
* Save reviewable suggestions without modifying accepted themes directly.

## Key distinction

```text
Topic = what an input or segment is about
Theme = what multiple related inputs are collectively saying
```

Topics and themes are stored separately but linked because their relationship may be many-to-many.

## Design principles

* Keep the database minimal.
* Preserve original text.
* Store segments separately from inputs.
* Store full-input and segment embeddings in PostgreSQL.
* Use statuses to control processing stages.
* Avoid tightly coupling workers.
* Start with sequential or scheduled workers.
* Add a queue only when continuous processing, retries or scaling are needed.
* Prefer existing topics and themes before creating new ones.
