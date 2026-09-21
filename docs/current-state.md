# Current state

The application is a batch-taxonomy editorial system. Inputs are prepared by
eligibility/segmentation and embedding workers; the scheduler automatically
snapshots eligible evidence, builds a leased candidate, and publishes only
after its immutable quality gate passes. Exactly one published run serves every
taxonomy reader and article-generation target. Before first publication,
taxonomy readers return a bounded first-run status; a failed gate reports a
bounded quality-blocked status while retaining any prior published run.

Incremental per-input topic assignment and live theme materialisation have
been removed. `worker_jobs` is limited to evidence preparation. Historical
incremental classifications and retired rollout records exist only in the
immutable, protected `taxonomy_legacy_archive`; they are never a reader
fallback.

Human publication defaults off and requires a configured mutation token. The
automatic transition is database-gated by an immutable passing attestation and
durable policy decision. Rollback remains explicit and preserves publication
decisions. See [Architecture](architecture.md),
[API reference](api.md), and [Operations](operations.md) for the supported
contracts and procedures.

Historical plans are in [the archive](archive/work-packages.md).
