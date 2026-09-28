# Architecture

This document shows how submitted answers become taxonomy and public content.
It describes the desired system as one input journey. Delivery status belongs
in [the work packages](work-packages.md); deployed differences belong in
[current state](current-state.md); implementation rules belong in the
[architecture contracts](architecture-contracts.md).

## Input journey

```text
Google Forms → response sheets → poll unread rows ┐
                                                  ├→ store each answer
Direct API input ─────────────────────────────────┘
    → check eligibility
    → split answers that contain multiple ideas
    → turn each evidence item into a semantic vector
    → freeze the available evidence into a taxonomy snapshot
    → cluster similar evidence within each question
    → name each coherent cluster as a provisional topic
    → merge equivalent topics found across different questions
    → group related topics into optional themes
    → record classified and unclassified coverage
    → publish one consistent taxonomy
    → use its evidence to generate draft articles
    → human review and approval
    → public pages
```

## 1. Capture inputs

- Google Forms → response sheets → poll only unread rows — avoids importing the
  same response twice.
- One non-empty answer cell → one stored input — keeps each question and answer
  independently analysable.
- Sheet heading → question context — gives meaning to short answers such as
  “No” or “Price”.
- Sheet row → submission identity — keeps answers from one respondent grouped.
- Sheet row + column → stable source identity — makes repeated polling safe.
- Direct API input → the same stored-input path — keeps one processing pipeline.
- Stored input → unchanged original answer — preserves the source evidence.

## 2. Prepare evidence

- Answer + question context → eligibility check — removes spam, gibberish,
  unrelated text, and administrative content from analysis.
- Responsive answer, even when short → eligible evidence — useful input does
  not need to be a complete sentence.
- One idea → keep the whole answer as one evidence item — retains context.
- Multiple independent ideas → split into separate evidence segments — lets
  each idea belong to a different topic.

Segments follow four rules:

- Each segment must make sense as an answer on its own.
- Qualifiers, examples, conditions, locations, and negation stay with the idea
  they modify.
- Wording is copied from the answer; question wording is never added.
- Segments stay in source order, do not overlap, and together retain the whole
  substantive answer.

If an answer is split, its segments become the evidence used by the taxonomy.
Otherwise, the full answer is used. The parent answer and its segments are
never counted together.

## 3. Represent meaning

- Evidence item → semantic vector — allows meaning-based comparison rather than
  exact-word matching.
- Answer-focused vector + retained question context — prevents repeated question
  wording from dominating clusters while keeping terse answers understandable.
- One taxonomy run → one compatible vector model and representation — prevents
  unlike vectors from being mixed.

## 4. Build a taxonomy candidate

- Prepared evidence → wait for a minimum amount and a quiet period — avoids
  starting while inputs are still arriving or being prepared.
- All eligible evidence at one cutoff → immutable cumulative snapshot — makes
  the candidate reproducible and ensures replacements use the complete dataset.
- Snapshot → group evidence by question — prevents unrelated questions from
  producing shared clusters.
- Each question group → semantic clusters — collects answers expressing the
  same specific concept.
- Cluster quality checks → coherent clusters or unresolved evidence — prevents
  weak, mixed, or unstable groups from becoming topics.
- Evidence outside a usable cluster → noise — avoids forcing every answer into
  a topic.

## 5. Create topics

- Coherent cluster → bounded evidence packet — gives the model enough central
  and varied examples without an unbounded prompt.
- Evidence packet + question context → LLM topic name and description — lets
  semantic interpretation handle synonyms and varied wording.
- Model response → structural and provenance checks — verifies valid output and
  membership without pretending word overlap proves meaning.
- Accepted response → provisional topic — preserves the question-level result
  before cross-question reconciliation.
- Rejected response → unclassified evidence with a review record — keeps useful
  results publishable without hiding uncertainty.

## 6. Reconcile topics and themes

- Provisional topics across questions → compare plausible equivalents — finds
  the same concept expressed through different questions.
- Equivalent topics → one canonical topic with their combined evidence — avoids
  duplicate topics without losing support or provenance.
- Related but meaningfully different topics → remain separate — preserves
  distinctions that matter.
- Related canonical topics → optional theme — provides broader navigation
  without forcing every topic into a theme.

## 7. Publish the taxonomy

- Candidate → coverage summary — records total, classified, unclassified, and
  noise evidence, plus question and submission counts.
- Topics + coverage + provenance → immutable quality attestation — makes the
  publication decision auditable.
- At least one valid canonical topic + passing attestation → publishable run —
  allows useful partial results without presenting them as complete.
- Passing run → atomically replace the previous published run — gives every
  reader one consistent taxonomy.
- Failed run → keep the previous publication — prevents a failed replacement
  from interrupting readers.

Inputs have three states relative to the published taxonomy:

- Classified → included in the snapshot and attached to a canonical topic.
- Unclassified → included in the snapshot but not attached to a canonical topic.
- Pending → arrived after the published snapshot.

## 8. Turn taxonomy into outputs

The published taxonomy produces two outputs.

### Administrative output

- Published run → topics, themes, evidence, coverage, and recommendations —
  gives editors one consistent view of the available insight.
- Candidate details → protected review view — exposes failures and provenance
  without making source evidence public.

### Public content output

- Published topic or theme → freeze its evidence and article template — keeps a
  generation job stable even when the taxonomy later changes.
- Frozen evidence → LLM article draft — grounds the draft in known evidence.
- Draft → validate citations and taxonomy references → render safe HTML — keeps
  generated claims and markup inside the approved boundaries.
- Generated article → editorial review — keeps publication a human decision.
- Human approval → immutable public article snapshot — prevents later taxonomy
  or article edits from silently changing published content.
- Approved snapshot → allowlisted public pages — exposes articles without
  exposing evidence, prompts, administration, or operational APIs.

## Architectural guardrails

- Original answers, taxonomy snapshots, model provenance, and approved article
  revisions remain traceable and immutable.
- PostgreSQL owns lifecycle and publication decisions; models can propose
  content but cannot publish it.
- Evidence work, taxonomy stages, and article generation use durable leases and
  retries so crashes do not duplicate committed results.
- A replacement taxonomy is built separately; the existing publication remains
  live until the replacement passes and swaps atomically.
- Admin, API, database, model, and review surfaces remain private. Only the
  allowlisted public article projection reaches the public edge.
- Retired incremental taxonomy data remains in a protected audit archive and is
  never used as a live reader fallback.

## System boundaries

```text
google-sheets poller → FastAPI input endpoint

admin-web → FastAPI → PostgreSQL + pgvector
                    → Ollama chat and embeddings
                    → evidence workers
                    → taxonomy scheduler
                    → article-generation worker

public-web → allowlisted server-rendered pages only
```

Ownership follows these boundaries: FastAPI owns HTTP validation, workers own
background processing, taxonomy modules own taxonomy construction, model
clients own Ollama communication, PostgreSQL migrations own durable invariants,
and the public projection owns public visibility.
