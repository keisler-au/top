# Taxonomy recovery and lifecycle repair

## Feature contract

Status: in_progress, 2026-09-21. User requests diagnosis and repair of the
persistent first-run dashboard error, with clarification of product decisions.
Baseline: `157eeb3909c175c6fec98a3248f05c819549fdae`, dirty tree containing
uncommitted automatic taxonomy implementation, migrations 039/040, dashboard
and operations changes, Compose changes, and architecture/delivery documentation.
Preserve that work. No data deletion or quality-gate bypass is authorized.

Live read-only evidence: run 1 is running, final readiness stage failed three
times with valueerror; quality stage wrote a release attestation but no legacy
quality snapshot. Gate failed topic acceptance (1/3); two labels failed literal
representative support. Scheduler is healthy but cannot progress.

Owners: taxonomy_stages, taxonomy_scheduler, taxonomy_automation,
taxonomy_snapshots, taxonomy_stage_quality, dashboard/operations API and admin
error normalization. Applicable contracts AC-01 through AC-04, AC-06 through
AC-09. Existing publication functions and immutable audit records remain owners.

Inputs/outputs: eligible canonical evidence -> immutable candidate -> leased
stages -> attested reviewable candidate -> gated publication; bounded API errors
must distinguish active work from terminal failure. Retry preserves frozen
outputs and releases/reacquires the existing singleton queue slot atomically.

Open decision: cumulative historical versus post-publication-only evidence;
asked user before changing membership policy. Deployment/recovery will be
presented only after a concrete tested change. No automatic mutation of old
attestations or accepted/rejected naming results.

## Pipeline

| Package | Status | Dependencies | Output / acceptance |
| --- | --- | --- | --- |
| TR-1 lifecycle and diagnostics | in_progress | current schema and observed failure | readiness uses actual quality owner; terminal failures/cancellation free queue; explicit retries work; truthful API status |
| TR-2 automation review | in_progress | canonical snapshot owner; user evidence policy | replay after interrupted snapshot/queueing; bounded retry policy; no loss of eligible evidence |
| TR-3 integrated verification and recovery | planned | TR-1/TR-2 | isolated PostgreSQL lifecycle, frontend checks, documentation, concrete operational recovery |

## Acceptance and handoff

- [ ] TR-A1: real quality computation -> readiness succeeds for pass and fail;
  passing candidate publishes through existing DB gate, failing candidate does not.
- [ ] TR-A2: stage failure/cancellation and explicit retry keep run/job/stage
  consistent; stale claims cannot change results; transaction rollback verified.
- [ ] TR-A3: crash replay and eligibility changes cannot strand automation;
  unchanged failed evidence never causes an automatic creation loop.
- [ ] TR-A4: dashboard/operations distinguish quality block, candidate failure,
  and genuine first-run processing, with frontend error tests and build.
- [ ] TR-A5: affected documentation and links checked; exact test commands,
  results, limitations and live recovery recorded before closure.

Next action: repair obsolete readiness check and add database regression tests,
then trace automation and its consumers. Verification pending; not deployed.
