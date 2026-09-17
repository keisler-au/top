# Current state

The application is a batch-taxonomy editorial system. Inputs are prepared by
eligibility/segmentation and embedding workers; an operator creates an
immutable evidence snapshot, and the taxonomy scheduler builds a candidate
run through leased stages. Exactly one gate-attested, explicitly published run
serves every taxonomy reader and article-generation target. Before first
publication, taxonomy readers return `taxonomy_unavailable`.

Incremental per-input topic assignment and live theme materialisation have
been removed. `worker_jobs` is limited to evidence preparation. Historical
incremental classifications and retired rollout records exist only in the
immutable, protected `taxonomy_legacy_archive`; they are never a reader
fallback.

Publication defaults off and requires a configured mutation token, an
immutable passing quality attestation, and an explicit operation. Rollback is
also explicit and preserves publication decisions. See [Architecture](architecture.md),
[API reference](api.md), and [Operations](operations.md) for the supported
contracts and procedures.

The remaining approved delivery work is the public website programme in
[current work packages](work-packages.md). Historical plans are in
[the archive](archive/work-packages.md).
