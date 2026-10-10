# Architecture

This document shows how submitted answers become taxonomy and public content.
It describes the desired system as one input journey. Delivery status belongs
in the [work-package archive](archive/work-packages.md); deployed differences belong in
[current state](current-state.md); implementation rules belong in the
[architecture contracts](architecture-contracts.md).

## Input journey

```text
Google Forms → response sheets → poll unread rows ┐
                                                  ├→ store each answer
Direct API input ─────────────────────────────────┘
    → exclude answers that do not respond to their question
    → split answers that contain multiple ideas
    → turn each evidence item into a semantic vector
    → freeze the available evidence into a taxonomy snapshot
    → cluster similar evidence within each question
    → name each coherent cluster as a provisional topic
    → merge equivalent topics found across different questions
    → group related topics into optional themes
    → record how much evidence has a topic
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
- Every input → immutable question context — ensures all evidence can be
  compared within the question it answered.
- Sheet row → submission identity — keeps answers from one respondent grouped.
- Sheet row + column → stable source identity — makes repeated polling safe.
- Direct API input → the same stored-input path — keeps one processing pipeline.
- Stored input → unchanged original answer — preserves the source evidence.

## 2. Prepare evidence

- Answer + question → decide whether the answer responds to the question —
  excludes spam, gibberish, unrelated text, and administrative text.
- Non-responsive answer → retain without an embedding — preserves the input
  without allowing it to shape the taxonomy.
- Responsive answer, even when short → prepare as evidence — useful answers do
  not need to be complete sentences.
- One idea → one evidence item — keeps the answer intact.
- Multiple ideas that could have different topics → one evidence item per idea
  — lets each idea receive the right topic.

An **evidence item** is the text used to build the taxonomy. It is either the
whole answer or one part of a split answer. Splitting follows three rules:

- Keep words together when separating them would change their meaning.
- Do not rewrite the answer or add words from the question.
- Keep the original order, do not duplicate text, and do not omit meaningful
  content.

These wording rules apply only when preserving source evidence. They do not
restrict topic or theme wording. Topics and themes are created from meaning and
may use words that do not appear in the answers.

If an answer is split, only its evidence items enter the taxonomy. If it is not
split, the whole answer enters. The whole answer and its split parts are never
counted together.

## 3. Represent meaning

- Prepared evidence item → semantic vector — allows meaning-based comparison
  rather than exact-word matching.
- Versioned question-answer vector + immutable per-question clustering — keeps
  terse answers understandable without allowing different questions to share a
  cluster.
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
- Evidence outside a usable cluster → remains without a topic — avoids forcing
  every answer into a group.

## 5. Create topics

- Coherent cluster → bounded evidence packet — gives the model enough central
  and varied examples without an unbounded prompt.
- Evidence packet + question context → LLM topic name and description — lets
  semantic interpretation handle synonyms and varied wording.
- Model response → format and evidence-link checks — verifies that the response
  is usable and refers only to evidence from its cluster; word overlap is not
  used to judge meaning.
- Accepted response → provisional topic — preserves the question-level result
  before cross-question reconciliation.
- Rejected response → evidence remains without a topic and gains a review
  record — keeps useful results publishable without hiding uncertainty.

## 6. Reconcile topics and themes

- Provisional topics across questions → compare plausible equivalents — finds
  the same concept expressed through different questions.
- Equivalent topics → one canonical topic with their combined evidence — avoids
  duplicate topics without losing supporting evidence or traceability.
- Related but meaningfully different topics → remain separate — preserves
  distinctions that matter.
Similarity shortlisting uses centroid cosine similarity of at least 0.82 or
name-term similarity of at least 0.50, across question scopes. These checks
select comparisons; the model decides equivalence. Each deterministic packet
contains at most 12 topics and at most two whole representative answers per
topic within 32,768 serialized bytes. Isolated topics bypass the model.
Overlapping packets must agree on one complete partition; contradictory
transitive merges fail before any canonical revision is stored.

Canonical revisions retain immutable provisional antecedents and the exact
union of their cluster evidence. Evidence counts, question counts and distinct
submission counts remain separately derivable. Replacement identity uses
source-evidence overlap with the prior publication, with explicit new,
continuation, rename, split, merge and retirement lineage.

- Related canonical topics → optional theme — provides broader navigation
  without forcing every topic into a theme.

Theme comparison uses deterministic neighborhoods of two to five canonical
revisions with up to two representative answers each within 32,768 serialized
bytes. An explicit no-theme decision, one topic, or isolated topics yields no
theme. A created theme links at least two distinct supplied canonical revisions.
Inference and reconciliation retain immutable attempts and antecedents.


## 7. Publish the taxonomy

- Candidate → coverage summary — records total evidence, evidence with a topic,
  evidence without a topic, plus question and submission counts. Coverage is
  information, not a minimum score required for publication.
- Candidate → internal consistency checks — confirms that every processing
  step finished, every topic refers only to evidence in this candidate, every
  result can be traced to its inputs, and the counts add up.
- At least one valid topic + passed consistency checks → publishable taxonomy —
  publishes useful results while preventing incomplete or internally broken
  data from becoming current.
- Passing run → atomically replace the previous published run — gives every
  reader one consistent taxonomy.
- Failed run → keep the previous publication — prevents a failed replacement
  from interrupting readers.

The quality owner uses the shared database facts function to verify completed
processing, exact evidence unions and their naming/reconciliation/model traces.
It records one immutable `taxonomy-release-gate-v3` attestation with evidence,
question, known submission, canonical topic, naming-attempt and theme counts.
The input hash binds those aggregates and the release policy. A retry reads the
stored attestation; historical versions remain unchanged. Coverage and rejected
attempts explain the result without adding input lifecycle states.


Inputs do not have a taxonomy classification state. The published run supplies
their current topic and theme associations. Empty topic and theme lists are a
normal result. A later run may assign, remove, or change those associations
without mutating the input or any earlier run.

**Full topic coverage** means every evidence item in the candidate has a topic.
**Partial topic coverage** means at least one evidence item does not. Both may
be published. These terms describe coverage only; they do not describe whether
processing finished successfully.

## 8. Turn taxonomy into outputs

The published taxonomy produces two outputs.

### Administrative output

- Published run → topics, themes, evidence, coverage, and recommendations —
  gives editors one consistent view of the available insight. Input responses
  retain processing status and run provenance, with deduplicated sorted topic/
  theme arrays and empty lists where no association exists. `taxonomy_state`
  is removed. Dashboard/operations report exact evidence coverage counts.
- Inputs view → published-run topic/theme arrays and independent processing
  status — renders empty associations normally without inventing a taxonomy state.
  Server-side attribute filters combine before paging; topic/theme filters use
  the same published-run associations as the displayed arrays.
- Internal read-only review → canonical topics, provisional antecedents,
  merge relationships, cluster support/reason codes and explicitly requested
  canonical evidence — loads without a token; raw model audit payloads are
  omitted and public-edge access remains denied. Review may inspect historical runs; ordinary browsing
  and generation still resolve the one published run. Browsing and generation
  default to topics; themes remain optional.

### Public content output

- Published topic or theme → freeze its evidence, run and article template in
  one database snapshot — keeps a generation job stable even when the taxonomy
  later changes. Topics can generate articles with no themes; article topic
  validation uses the recorded run.
- Frozen evidence → LLM article draft — grounds the draft in known evidence.
- Draft → validate citations and taxonomy references → render safe HTML — keeps
  generated claims and markup inside the approved boundaries.
- Generated article → editorial review — keeps publication a human decision.
- Human approval → immutable public article snapshot — prevents later taxonomy
  or article edits from silently changing published content.
- Approved snapshot → allowlisted public pages — exposes articles without
  exposing evidence, prompts, administration, or operational APIs.

## Architectural guardrails

- Original answers, taxonomy snapshots, model trace records, and approved article
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

Local `docker compose up` includes all services through the automatic development
override. Source edits reload Python and recompile the admin frontend; explicit
`-f compose.yaml` selects production images and optional admin/Sheets profiles.
The development runtime preserves queue ownership, persistent volumes and the
public allowlist. See [ADR-0005](decisions/0005-default-local-development.md).

## System boundaries

```text
google-sheets poller → FastAPI input endpoint

admin-web → FastAPI → PostgreSQL + pgvector
                    → Ollama chat and embeddings
                    → background evidence processes
                    → taxonomy scheduler
                    → article-generation worker

public-web → allowlisted server-rendered pages only
```

Ownership follows these boundaries: FastAPI owns HTTP validation, background
processes own long-running work, taxonomy modules own taxonomy construction,
model clients own Ollama communication, PostgreSQL migrations own durable
invariants, and the public projection owns public visibility.
