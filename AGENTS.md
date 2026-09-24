# Repository contracts for agents

## Start here

Before planning or implementing, read [the documentation guide](docs/README.md),
[current state](docs/current-state.md), [architecture](docs/architecture.md),
[architecture contracts](docs/architecture-contracts.md), and
[delivery contracts](docs/delivery-contracts.md). Read the API, operations, and
frontend references for the surfaces you touch. If `docs/work-packages.md`
exists, read its feature contract, dependency table, and selected package.
Archived plans are historical evidence, never current instructions.

Inspect `git status --short` and the relevant code and tests before changing
anything. Preserve existing work. Record the starting revision and relevant
uncommitted changes; HEAD alone does not describe a dirty working tree.

## Required behaviour

- Apply architecture contracts by their `AC-*` IDs. Existing inconsistencies
  are recorded in [the baseline review](docs/reviews/architecture-baseline.md);
  they are not patterns to copy or permission for unrelated refactoring.
- Use the existing owner of a capability. Trace its callers, SQL constraints,
  background jobs, API consumers, and public exposure before extending it.
  Do not create a second implementation of a shared rule in a new feature.
- Follow the small-change or feature workflow in the delivery contracts.
  Establish package inputs, outputs, invariants, and acceptance evidence before
  implementation. A package may refine the global contracts, not silently
  override them.
- At each resumed session, revalidate dependencies and assumptions against
  the current checkout. Update the plan when evidence changes. Continue work
  already authorized; ask only when resolving a conflict requires a new
  product decision or an expansion of authorized scope.
- For boundary changes, write a decision using the
  [decision template](docs/templates/architecture-decision.md), update the
  contracts and affected consumers together, and identify migration/recovery.
  Do not mark an unchosen proposal accepted.
- Verify behaviour at the boundary affected. Skipped database or public-edge
  tests are not proof of integration. Record exact commands, outcomes, skips,
  and limitations; never inherit another package's passing result as your own.
- Close a package only when every acceptance criterion has evidence, reference
  documentation is current, and the next package's assumptions still hold.
  Record a durable handoff in the plan before ending the session.

## Docker Compose command authorization

Within otherwise authorized repository work, every command whose command line
starts with `docker compose` has standing user authorization and does not need
separate confirmation. Do not pause merely to ask permission before running
such a command. This standing authorization does not expand the requested
product scope or independently authorize deletion of persistent data. Any
approval that the execution environment itself requires still applies.

These rules govern repository work; they do not authorize deployment, data
deletion, or additional product scope. Documentation-only work requires link
and consistency checks, not a gratuitous full application test run.
