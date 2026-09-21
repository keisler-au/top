# Feature plan template

Copy the content below into `docs/work-packages.md`, or merge it into the
existing current plan. Replace placeholders; use `not applicable: <reason>`
where justified. This template is not an active delivery plan.

## Feature contract: <feature ID and outcome>

- Status / last updated:
- User request and authorized scope:
- Outcome and feature-level acceptance IDs:
- Non-goals:
- Baseline revision and relevant uncommitted work:
- Current behaviour and evidence (code/tests):
- Proposed behaviour and existing owners to extend:
- Applicable AC IDs and decision records:
- Open decisions, assumptions and risks:
- Migration/deploy order, compatibility window and recovery:

| Interface / data / setting | Owner | Before → after | Producers and consumers | Compatibility / verification |
| --- | --- | --- | --- | --- |
| <exact endpoint, function, table, job or setting> | <module> | <contract> | <all affected callers/readers> | <strategy and acceptance ID> |

## Pipeline

| Package | Status | Dependencies and required outputs | Outputs / consumers | Completion evidence |
| --- | --- | --- | --- | --- |
| <ID> | planned | <ID + concrete prerequisite, or none> | <interface/behaviour unlocked> | <acceptance IDs/results> |

Next ready package: <ID and why its entry conditions hold>.
Integration owner/package: <ID and complete user journey it verifies>.

## Package <ID>: <observable outcome>

### Entry and scope

- Objective and non-goals:
- Dependency outputs verified (paths/interfaces/versions):
- Expected modules/files and owners:
- Applicable AC IDs / decisions:
- Baseline rechecked on / drift discovered / resolution:

### Local contract

- Inputs and outputs (wire/storage types, identity, errors, consumers):
- Invariants and transaction boundaries:
- State transitions, leases, idempotency and concurrency:
- Authorization, private/public data exposure:
- Failure/retry/recovery and rollout:
- Compatibility and downstream package impacts:

### Work and acceptance

- [ ] <work item tied to acceptance ID>

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| <ID>-A1 | <given/when/then> | <exact check> | pending |

### Documentation and handoff

- References to update (or reason none):
- Delivered behaviour and interface changes:
- Tests passed/failed/skipped and unverified criteria:
- Decisions/drift and unresolved risks:
- Next package and concrete inputs, or exact remaining work/blocker:
- Completion reconciliation: objective, work, acceptance, references,
  downstream assumptions and pipeline status agree.

## Feature closure

- Integrated acceptance evidence:
- Temporary paths retired / intentional compatibility retained:
- Implemented / verified / merged / deployed status, separately:
- Final status and archive reason/date, including any undelivered scope:
