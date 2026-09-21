# Current work packages

**Status: active delivery plan.** This programme changes the completed
batch-taxonomy deployment from operator-started, operator-published batches to
automatic, quality-gated taxonomy delivery. It supersedes no production data
model: frozen evidence, leased stages, immutable release attestations, stable
identities, and rollback history remain the governing boundaries.

## Decision and approach

The existing implementation has already completed evidence preparation,
snapshotting, durable scheduler stages, and an immutable machine-computed
quality gate. The failure is an orchestration gap: no component creates the
first candidate run, and a passing candidate cannot be promoted without a
human API call and deployment switch. Adding a separate manual UI button would
preserve that gap and make first use fragile.

The selected approach is a small extension of the existing taxonomy scheduler,
not a new service or a shortcut around the gate:

```text
ready-for-analysis evidence
  -> durable automatic snapshot decision
  -> existing leased candidate stages
  -> existing immutable quality attestation
  -> atomic automatic promotion if, and only if, the gate passes
  -> one published run
```

Automation is enabled by default for the local Compose deployment. It creates
at most one active candidate at a time, records the automation policy and
decision durably, and never republish-loops a failed unchanged snapshot. A
failed gate leaves the current published run intact; on a first run it leaves
the taxonomy unavailable with a bounded, actionable status rather than a
generic server error. Explicit operator review, reject, retry, and rollback
remain available for exception handling, but are not required for ordinary
operation.

## Pipeline at a glance

| Package | Status | Dependency | Completion evidence to record here |
| --- | --- | --- | --- |
| AT-WP1 automatic snapshot orchestration | **Complete** | None | Migration `039`; automatic snapshot concurrency/replay, failed-candidate suppression, manual reconciliation, and full 191-test PostgreSQL+pgvector Compose verification passed |
| AT-WP2 attested automatic promotion | **Complete** | AT-WP1 | Migration `040`; automatic pass/fail, idempotent promotion, prior-run supersession, rollback eligibility, and token-bound manual publication verification passed |
| AT-WP3 operator-visible automation and delivery verification | **Planned** | AT-WP2 | Admin status contract, Compose end-to-end lifecycle run, and operations/reference-document review |

Work proceeds strictly in this order. Mark a package **Complete** only after
every objective, work item, and automated acceptance criterion has been
verified and its completion evidence is recorded immediately below the
package. When this final package is complete, archive this document under
`docs/archive/` and update `docs/archive/work-packages.md` before creating a
new current plan.

## Global invariants

- Canonical evidence selection remains transactional and uses segments instead
  of their parent original where segments exist.
- Every run preserves existing model, configuration, prompt, evidence, stage,
  quality-attestation, and publication-decision provenance.
- At most one candidate run is active; every reader resolves exactly one
  published run, never a candidate or legacy fallback.
- Automatic promotion can occur only after the existing immutable,
  server-computed quality attestation passes. The automation actor cannot
  supply or override gate metrics.
- A failed or unchanged candidate cannot cause an unbounded retry/publish
  loop. A failed replacement never withdraws the currently published run.
- Tokens remain required for privileged human operations. Normal ingestion,
  taxonomy creation, and qualified automatic promotion require no token or
  manual dashboard action.

## AT-WP1 — Automatic snapshot orchestration

### Objective

Create and schedule a candidate taxonomy run automatically whenever eligible
evidence needs classification, including the first run after a clean startup,
without creating duplicate or overlapping candidates.

### Work

- Define one versioned automation policy from deployment configuration. It
  includes enabled state, polling cadence, minimum eligible evidence, and a
  bounded quiet/debounce interval suitable for continuous input ingestion;
  local Compose enables it by default.
- Add additive durable state for the last considered/published evidence cutoff,
  policy version, automatic decision, and bounded failure reason. Make policy
  evaluation and candidate creation concurrency-safe across scheduler restarts
  and replicas.
- Extend the existing scheduler loop to evaluate the policy after evidence
  preparation has made canonical embeddings eligible. It must use the existing
  snapshot creator and run queue rather than duplicate snapshot SQL or bypass
  model/configuration provenance.
- Create the first candidate as soon as the policy is satisfied. For later
  runs, create a candidate only for evidence beyond the published cutoff and
  only after the debounce policy is satisfied. Do not create a replacement for
  an unchanged failed snapshot until new eligible evidence or an explicit
  operator retry changes the decision.
- Preserve the protected manual snapshot endpoint and CLI for recovery and
  investigations; make their interaction with the automatic checkpoint
  deterministic and observable.

### Automated acceptance criteria

- PostgreSQL tests prove a clean installation with eligible evidence creates
  exactly one automatic first candidate, queues it once, and survives repeated
  scheduler polls and restarts without duplicate runs or evidence membership.
- Tests prove a later candidate contains only canonical evidence newer than the
  published cutoff, honors the debounce/minimum-evidence policy, and cannot be
  created while another candidate is pending or running.
- Concurrent scheduler claims and a crash between decision and enqueue either
  recover the same durable decision or safely retry it; neither creates an
  orphaned snapshot nor loses eligible evidence.
- Tests prove a failed unchanged snapshot is not automatically recreated, and
  a manual snapshot/retry reconciles the durable automation checkpoint.

### Completion evidence

- Implemented versioned `TAXONOMY_AUTOMATION_*` policy controls, enabled by
  default in local Compose, with bounded minimum-evidence and quiet intervals.
- Migration `039_add_taxonomy_automation.sql` adds a singleton checkpoint and
  immutable-identity decision log. The scheduler reserves a durable decision
  before it calls the existing snapshot creator/queue, so concurrent polls and
  restart replay reuse the same key.
- PostgreSQL integration verifies one queued automatic replacement contains
  only evidence newer than the published cutoff, concurrent evaluators create
  no duplicate, a failed unchanged candidate remains blocked, and protected
  manual creation reconciles the checkpoint. `docker compose -f
  compose.test.yaml run --rm tests` passed: 191 tests.

## AT-WP2 — Attested automatic promotion

### Objective

Promote a qualifying automatic candidate to the sole published taxonomy
without a token, deployment switch, or human action, while retaining the same
quality threshold and durable publication audit trail.

### Work

- Replace the deployment-default-off publication block for automatic candidates
  with a narrowly scoped, database-enforced automation transition. Manual
  publication remains protected by the existing mutation-token contract.
- After the existing quality stage records a passing immutable attestation,
  atomically promote the ready candidate using a stable automation actor and
  policy version in the publication decision. Preserve optimistic lifecycle
  checks and supersede the prior published run in the same transaction.
- On a failed quality attestation, terminal stage failure, or policy-disabled
  deployment, retain the candidate and a bounded reason; do not publish it,
  replace the prior published run, or continually retry it.
- Ensure restart/replay safety: a scheduler may observe an already promoted
  candidate but cannot emit a second publication decision or create two
  published runs.

### Automated acceptance criteria

- PostgreSQL integration tests prove a passing attestation automatically
  publishes exactly one candidate and produces an immutable publication
  decision with the automation policy/version and no raw evidence or secrets.
- Tests prove every threshold failure prevents automatic publication and keeps
  an existing published run readable; a first-run failure leaves no false
  published projection.
- Concurrent/restarted scheduler tests prove publication is idempotent,
  preserves the one-published-run constraint, and retains rollback eligibility
  and prior decision history.
- Tests prove a human publish call remains token-protected and cannot use the
  automatic transition to bypass its authorization boundary.

### Completion evidence

- Migration `040_add_taxonomy_automatic_promotion.sql` introduces a narrowly
  scoped database transition: only an automatic decision whose policy version
  matches and whose immutable quality attestation passes can publish.
- The transition atomically supersedes the previous published projection,
  records `taxonomy-automation` plus policy version in one immutable decision,
  and returns an already-published candidate unchanged on replay.
- PostgreSQL integration covers passing automatic promotion, failed-gate
  preservation of the existing published run, one decision on replay, rollback
  eligibility, and token-protected human publication. Clean `docker compose
  -f compose.test.yaml run --rm tests` verification passed: 193 tests.

## AT-WP3 — Operator-visible automation and delivery verification

### Objective

Make automatic taxonomy progress and failures understandable at first use, and
prove the complete Compose deployment advances input to published taxonomy
without an operator action.

### Work

- Extend the bounded operations/dashboard status contract to distinguish
  preparing evidence, waiting for automation policy, running candidate,
  automatically published, and blocked-by-quality states. It must expose only
  aggregate counts, state, policy version, and bounded failure codes.
- Update the admin dashboard to render these states and a clear recovery path;
  replace the generic taxonomy `503` experience with an explicit first-run or
  blocked-quality message. Do not expose protected candidate detail or raw
  evidence to the public edge.
- Update Compose defaults, health checks, logs, and operations documentation
  for automatic mode, including how to pause automation and how operators
  inspect, retry, reject, or roll back exceptional candidates.
- Update architecture, API, root README, current-state, and admin README only
  when their described runtime/API/UI behaviour has shipped.

### Automated acceptance criteria

- A built Compose lifecycle test imports or seeds eligible inputs, waits for
  evidence preparation, verifies automatic snapshot and stage processing, and
  observes one gate-qualified published run without an API token or manual
  action.
- The same suite proves unavailable, waiting, running, failed-gate, and
  published statuses are bounded and correctly represented by the admin UI;
  the public edge exposes none of them.
- Compose restart/recovery tests verify an in-flight automatic run resumes and
  an existing published taxonomy remains available while a replacement fails.
- Documentation checks pass, including `git diff --check` and confirmation
  that `docs/work-packages.md` is the sole current work-package document.

## Explicit non-goals

- This programme does not automatically publish editorial articles; article
  approval remains an explicit editorial decision.
- It does not weaken, replace, or permit caller-provided quality signals.
- It does not expose taxonomy operations, evidence, or candidate data through
  the public website.
