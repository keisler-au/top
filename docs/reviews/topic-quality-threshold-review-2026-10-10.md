# Topic cohesion and stability threshold review

Date: 2026-10-10. Scope: explain the measurements and assess whether the current
cutoffs may reject useful groups. This is a review, not an accepted policy change.
The Inputs attribute-filter implementation remains separate from this review.

## Measurements in current source

`taxonomy_experiment.cluster_diagnostics` calculates a normalized centre from the
sum of the group's answer vectors. Cohesion is the average cosine similarity
between each member vector and that centre. For vectors v and centre c,
cosine similarity is `(v · c) / (length(v) * length(c))`. Current question-answer
vectors include the original question plus the whole answer or preserved segment.
The shared question can itself contribute similarity; this is a geometric
measure, not a direct test of human agreement or semantic correctness.

`cluster_passes_policy` requires mean cohesion at least 0.95 and HDBSCAN density
persistence at least 0.05. Equality passes. Missing, nonfinite and out-of-range
required measures also produce the corresponding failure code, so the code
alone does not establish that a valid numeric score was merely too low.
Persistence describes how the group persists across distance scales within the
clustering hierarchy. It is not repeat-run stability or a confidence probability.
The experiment also calculates cross-parameter pair retention, but that is not
the measure used by `stability_below_minimum`.

HDBSCAN documents persistence as a relative group-strength score from 0 to 1:
[official API reference](https://hdbscan.readthedocs.io/en/latest/api.html).
The code uses question-scoped normalized vectors, Euclidean HDBSCAN with default
minimum group size 2 and minimum samples 1. Failure rejects the entire group
before topic naming; stored source answers are retained.

## Existing calibration and assessment

The [2026-09-29 calibration](ptr0-representation-policy-calibration-2026-09-29.md)
used `nomic-embed-text`, 24 synthetic answers and 38 installed evidence items.
At the selected cutoffs, 4 of 8 synthetic groups and 5 of 7 installed groups
passed. One installed group failed cohesion and one failed stability.

| One cutoff changed; other checks unchanged | Synthetic groups accepted | Installed groups accepted |
| --- | ---: | ---: |
| Selected: cohesion 0.95, persistence 0.05 | 4 / 8 | 5 / 7 |
| Cohesion lowered to 0.93 | 4 / 8 | 6 / 7 |
| Persistence lowered to 0.03 | 4 / 8 | 6 / 7 |

These are independent sensitivity checks, not evidence that changing both
accepts all seven. The installed groups had no human-approved concept labels;
acceptance counts cannot show whether additional groups are useful or misleading.
The synthetic fixture did not demonstrate a loss of known good groups from
these cutoffs, but it is too small to establish general precision or recall.

Assessment: overly restrictive rejection is plausible, especially because a
single cutoff removes a whole group before semantic interpretation. Cohesion
0.95 is demanding geometric compactness, but its number alone cannot determine
strictness for this model. Persistence 0.05 is numerically low, yet its meaning
is relative to the data geometry. Neither cutoff is strongly established by
human-labelled production evidence. No current live rejected groups or scores
were inspected during this review; no new model experiment was run.

## Proposed next evidence

Review representative accepted and rejected groups with their actual scores,
questions and original answers; include groups just above/below both cutoffs.
Have people judge whether each supports one useful topic independently of the
scores. Compare selected and relaxed cutoffs on that same dataset and report
false rejection, misleading topics and evidence coverage, not just group counts.
Only then select and version a revised policy. Score/reason visibility would
also help managers distinguish weak grouping from missing diagnostics.

No thresholds, naming behaviour, stored runs or publication decisions changed.
