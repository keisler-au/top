# PTR-0 representation and topic-policy calibration

- Date: 2026-09-29
- Starting revision: `8b3910acdf88bddb87e4f10a41819c6bfad595b6`
- Dirty-tree context: pre-existing edits to `AGENTS.md`, architecture,
  architecture contracts, ADR-0003, and the active plan were preserved.
- Policy: `partial-topic-policy/v1`
- Fixture SHA-256: `029cff5e80f30275d1dfc7b3e816a6090d4dcb3fb63ee465992b1ee12c619ec0`
- Installed export SHA-256:
  `f62b21999b22694b26af9f3f6123614d67b15d3bb220d7df73e67874eaaf3c2a`
- Model: local `nomic-embed-text`, 768 dimensions. The configured labelling
  model was `qwen3:4b-instruct` with a reported 262,144-token context.

This is an offline calibration record, not a claim that production clustering
already implements the policy. No application row was changed. Installed text
and generated vectors stayed in a temporary directory; only aggregate results
appear here.

## Selected policy

`partial-topic-policy/v1` reuses the existing `question-answer` embedding made
from `Question: {question}\nAnswer: {answer}`. It creates clusters separately
for each immutable question, using normalized vectors and HDBSCAN with
`min_cluster_size=2`, `min_samples=1`, Euclidean distance, and one worker.
Question scope prevents different answers from being joined merely because
their questions differ, while context still gives meaning to terse answers.
No second embedding or backfill is required.

Each non-noise cluster must pass all applicable checks:

| Measure | Definition | Minimum |
| --- | --- | ---: |
| Cohesion | Mean cosine similarity from each member to the normalized cluster centroid | 0.95 |
| Separation | One minus cosine similarity to the nearest other centroid in the same question | 0.08; not applicable when there is no alternative cluster |
| Membership | Nearest-rank 10th percentile of HDBSCAN membership probability | 0.60 |
| Stability | HDBSCAN density persistence for the cluster | 0.05 |

A failed check leaves the evidence without a topic and records one or more of
`cohesion_below_minimum`, `separation_below_minimum`,
`membership_below_minimum`, or `stability_below_minimum`. It does not call the
topic model. Small two-member clusters are permitted and face the same measured
checks; size alone does not reject them.

The topic packet includes every distinct original input when there are at most
40. Larger clusters select 30 centroid-nearest originals, then up to 10 by
iterative farthest-first selection. Ordering and ties use the evidence ID. The
evidence-object payload is capped at 32,768 UTF-8 JSON bytes. A complete
at-most-40 packet or the required 30 central items that exceeds the cap fails
closed; evidence is never silently truncated. The 24-item fixture fit inside
the bound. The bound leaves a large fixed-prompt and response reserve in the
configured model, but PTR-2 must verify any replacement model's context.

Two provisional topics are equivalent when they discuss the same specific
concept and can use one neutral canonical label. Different expressed positions,
including support and opposition, remain traceable but do not by themselves
make different concepts. Different concepts in one domain are
`related-not-equivalent` and may later share a theme. Different concepts in
different domains are `distinct`. A model proposes this classification from
names, descriptions, questions, support, and bounded evidence; deterministic
code validates the non-overlapping partition and evidence links.

## Evidence

The committed fixture has 24 synthetic answers across four question types. It
contains synonyms, repeated concepts across different questions, identical
terse answers to different questions, and supporting and opposing positions.
At `min_cluster_size=2`, `min_samples=1`, the selected representation produced
eight candidate clusters. The policy accepted the four known housing-cost and
bus-frequency clusters and rejected four deliberately ambiguous terse clusters
on separation. Answer-only vectors produced nine candidates but only two
passed, mainly because cohesion fell below 0.95.

Context materially changed terse meaning: identical `Yes.` answers in two
questions had cosine similarity 1.000 as answer-only text and 0.765 with their
question; identical `No.` answers changed from 1.000 to 0.780. Equivalent
housing and bus concepts across different questions remained shortlistable at
0.779 and 0.844 respectively. Thus question context distinguishes terse text
without preventing cross-question reconciliation.

The read-only installed export contained 38 canonical evidence items across
three questions. Global contextual HDBSCAN reproduced three question-shaped
clusters with no noise, confirming why global clustering is invalid. Under the
selected per-question policy, seven candidates were found: five passed, one
failed stability, and one failed cohesion. Answer-only yielded eight candidates
and none passed cohesion. The installed corpus has no approved concept labels,
so these counts corroborate geometry only and are not semantic ground truth.

Sensitivity counts below show accepted candidates when one threshold changes:

| Change | Synthetic accepted (of 8) | Installed accepted (of 7) |
| --- | ---: | ---: |
| Selected values | 4 | 5 |
| Cohesion 0.93 / 0.97 | 4 / 4 | 6 / 3 |
| Separation 0.05 / 0.12 | 4 / 0 | 5 / 0 |
| Membership 0.50 / 0.80 | 4 / 3 | 5 / 5 |
| Stability 0.03 / 0.10 | 4 / 4 | 6 / 3 |

The selected separation value is below the known-good fixture range
(0.108–0.113) and above the ambiguous terse range (0.028–0.030). Installed
sensitivity shows that cohesion and persistence remain model/corpus-sensitive;
they must be recalibrated when the embedding model or representation changes.

## Reproduction and limitations

Focused automated evidence:

```bash
cd backend
UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m unittest tests.test_taxonomy_experiment -v
```

The synthetic vectors were generated with:

```bash
python -m triage_processor.taxonomy_experiment fixture \
  --fixture tests/fixtures/ptr0_calibration.json \
  --output /tmp/ptr0-calibration/synthetic.json \
  --embedding-model nomic-embed-text
```

The installed comparison used the experiment's `export
--answer-only-comparison` command at one fixed cutoff, followed by
`evaluate_question_scopes` over `(2,1)`, `(3,1)`, `(3,2)`, and `(4,2)`. Raw
installed evidence was not committed and the temporary copy was removed after
the aggregate review. There was no external labelled corpus or human semantic
annotation of installed data. Consequently the numeric policy is approved only
for the named model, representation, fixture, and current installed aggregate;
a model or representation change requires a new policy version and calibration.
