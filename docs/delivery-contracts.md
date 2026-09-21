# Feature and work-package contracts

The goal is that a fresh agent can continue tomorrow without inventing the
architecture again. Global [architecture contracts](architecture-contracts.md)
apply to every change; each package adds a concrete local contract.

## DC-01 — Source of authority

Current user instructions establish scope. Root `AGENTS.md`, architecture
contracts and accepted decisions govern implementation. The current plan
defines delivery sequence within those boundaries. Reference documents describe
implemented behaviour; code, migrations and tests are evidence of what exists.
Archive documents and code comments may be stale and cannot override current
contracts. When these disagree, record the discrepancy and resolve it using
evidence; do not silently choose the easiest interpretation.

Use at most one `docs/work-packages.md`. No active feature means no such file;
templates and review findings do not constitute an active plan. Several approved
features can share that plan with distinct IDs and explicit cross-dependencies.

## DC-02 — Scale the process to the change

For a small change within existing boundaries, put a short contract in the
change description (or the current plan if it already tracks the work):

```text
Outcome and non-goals:
Baseline and existing owner:
Affected AC IDs and interfaces (or none, with reason):
Acceptance checks and documentation impact:
Completion evidence / remaining work:
```

Do not create a programme or decision record for a text fix, isolated bug fix,
or local implementation choice that preserves existing contracts.

Use a feature contract and work packages for work spanning sessions/components,
changing persistence/public interfaces, introducing a lifecycle, or requiring
architecture/migration decisions. Use the
[feature and package template](templates/feature-plan.md). Use a
[decision record](templates/architecture-decision.md) for a changed boundary,
durable identity, publication/security rule, major dependency or competing
architecture choices. Reference decisions from the plan; avoid copying their
text into every package.

## DC-03 — Feature contract before decomposition

Record the user outcome, non-goals, baseline revision plus dirty-tree context,
existing owners, affected AC IDs, before/after behaviour and decisions. Inventory
producers and consumers of every changed interface: routes, SQL functions,
tables, jobs, settings and frontend/public readers. Specify compatibility,
rollout/recovery, risks and feature-level acceptance.

Break the feature into packages only after those boundaries are explicit.
Each dependency identifies the concrete output consumed, not merely a package
number. Intermediate packages must leave the repository coherent; if a feature
is incomplete, gate its exposure and state who integrates it. The final package
proves the complete user journey and removes temporary compatibility paths
when their stated retirement condition is met.

## DC-04 — Package entry and daily resumption

Before changing code:

1. Inspect the working tree and reread the feature contract and selected package.
2. Verify predecessor outputs exist and their interface/version still matches.
3. Compare the current code, schema and consumers to the recorded assumptions.
4. Record any drift, update affected packages and choose the smallest aligned
   implementation within authorized scope. A new product decision remains open
   until resolved; independent authorized work may continue.
5. Mark the package in progress and maintain its acceptance checklist.

A package is ready only when its objective, non-goals, inputs, outputs,
affected owners/contracts, dependencies and verification are concrete. Unknowns
may be an explicit investigation package with a decision as its output; they
must not masquerade as a ready implementation contract.

## DC-05 — Local implementation contract

Every package records:

- Ownership and allowed surfaces; the files/modules expected to change are a
  scope guide, not a prohibition on necessary supporting edits.
- Input/output contracts: exact schema/function/endpoint/job and consumers,
  including identity, nullability, errors and compatibility where applicable.
- Relevant invariants and transaction/lease/authorization responsibilities.
- Failure, retry, concurrency and recovery behaviour, or explicit reasons
  these do not apply.
- Acceptance IDs tied to observable behaviour and named verification commands.
- Documentation impact and outputs that unlock downstream packages.

If implementation changes an agreed interface, update the feature contract,
decision and affected downstream packages before relying on the new interface.
Do not substitute a mock, placeholder, duplicate service or manual step for an
accepted end-to-end criterion and then mark the package complete.

## DC-06 — Evidence and completion

Use `planned`, `ready`, `in_progress`, `blocked`, and `complete` consistently.
`blocked` includes the exact missing input and work remaining. A package moves
to `complete` only when every objective/work/acceptance item is reconciled,
affected references are updated, and downstream assumptions have been checked.
Implementation finished with verification pending remains `in_progress` or
`blocked`, with the reason recorded.

For each acceptance ID record command/test, date, result including skips,
environment, and revision or working-tree description. Link existing tests
instead of copying old pass counts. Distinguish implemented, tested, merged
and deployed; one does not imply another. Do not claim a test run against a
revision that predates the tested changes.

Useful existing commands (run from repository root unless stated):

```bash
# Backend; database/edge cases may skip without their test environment.
cd backend
uv run python -m unittest discover -s tests -v
```

```bash
# Admin, from frontend/admin/.
npm run typecheck
npm test
```

```bash
# Full isolated database/public-edge verification, from repository root.
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
git diff --check
```

Select the relevant checks using AC-09. Database integration fixtures can
delete data: use only the disposable test stack/test database, never an
application database. When fresh initialization is required, ensure the test
PostgreSQL instance is fresh; an already-running container is not that evidence.

The closing handoff states delivered behaviour, changed interfaces, acceptance
results, unresolved risks, drift/decisions, and the next ready package with its
concrete inputs. If work remains, record its exact location and next action.
Do not rely on chat history for the next day's agent.

## DC-07 — Plan completion and archive

Before declaring a feature complete, verify its integrated acceptance criteria
as well as package criteria. Reconcile the pipeline table, package bodies,
current-state reference and archive index. Archive a completed plan only with
its final status, date, reason and evidence intact.

Do not replace an incomplete current plan silently. Explicit user cancellation
or supersession may close remaining packages as cancelled/superseded, with
undelivered scope and any transferred work recorded; never relabel them complete.
An archived proposal is not permission to revive its old runtime design.
