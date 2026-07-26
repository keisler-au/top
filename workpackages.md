# Question-Context Implementation Plan (v3)

This revision retains v2's question-context design and tightens the WP6/WP7
theme flow: topic aggregation now uses complete, stable membership;
suggestions have durable materialization state and backlog replay; update and
merge naming is explicit; merge aliases are path-compressed; and the existing
many-to-many topic/theme cardinality is reflected consistently in reads.
Changes are called out inline where they reverse or correct an earlier
version.

## Design decisions locked in

- **Themes are always globally scoped and always inferred.** No
  `target_theme` field exists anywhere in the schema or payload.
- **Theme grouping now operates at the topic level, not the raw-answer-embedding
  level** (see WP6 — this is a correction from v1).
- **Topics are question-aware and fine-grained.** "Cost Barriers" is derived
  from a specific answer in the context of its specific question. Topics
  carry question-specific meaning; themes abstract across questions and
  topics.
- **Question identity** is `(source, form_key, question_key, question_version)`.
  `question_text` is an immutable snapshot.
- **Question context is normalized** into a `questions` table;
  `original_inputs` holds a nullable, immutable-once-set FK to it.
- **Each input/segment has exactly one embedding, always** (see WP1 — this
  reverses v1's representation-versioning uniqueness relaxation).
- **Generic inputs are untouched** at every pipeline stage.

---

## WP1 — Database schema normalization

### New table: `questions`

```sql
CREATE TABLE questions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source TEXT NOT NULL
        CONSTRAINT questions_source_nonempty CHECK (btrim(source) <> ''),
    form_key TEXT NOT NULL
        CONSTRAINT questions_form_key_nonempty CHECK (btrim(form_key) <> ''),
    question_key TEXT NOT NULL
        CONSTRAINT questions_question_key_nonempty CHECK (btrim(question_key) <> ''),
    question_version INTEGER NOT NULL DEFAULT 1
        CONSTRAINT questions_version_positive CHECK (question_version >= 1),
    question_text TEXT NOT NULL
        CONSTRAINT questions_text_nonempty CHECK (btrim(question_text) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT questions_identity_unique
        UNIQUE (source, form_key, question_key, question_version)
);

CREATE INDEX idx_questions_source_form ON questions (source, form_key);
```

- `idx_questions_source_form` supports "all questions for this form"
  lookups (used by WP7). The identity unique index's leftmost-prefix
  property (`source, form_key, question_key, question_version`) already
  supports "all versions of this question" lookups without a separate
  index — no `question_version` filter needed to use it efficiently.
- No `updated_at`, no UPDATE route. Enforce immutability at the DB level:

```sql
CREATE OR REPLACE FUNCTION reject_question_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'questions rows are immutable; insert a new question_version instead';
END;
$$;

CREATE TRIGGER questions_immutable
BEFORE UPDATE ON questions
FOR EACH ROW EXECUTE FUNCTION reject_question_mutation();
```

### Changes to `original_inputs`

```sql
ALTER TABLE original_inputs
    ADD COLUMN question_id BIGINT
        REFERENCES questions (id) ON DELETE RESTRICT,
    ADD COLUMN submission_key TEXT
        CONSTRAINT original_inputs_submission_key_nonempty
        CHECK (submission_key IS NULL OR btrim(submission_key) <> '');

CREATE INDEX idx_original_inputs_question_id
    ON original_inputs (question_id)
    WHERE question_id IS NOT NULL;

CREATE INDEX idx_original_inputs_submission_key
    ON original_inputs (submission_key)
    WHERE submission_key IS NOT NULL;
```

**Correction from v1: enforce `question_id` immutability at the DB level.**
Nothing previously stopped an application bug from re-pointing an existing
answer at a different question after creation, which would silently corrupt
history. Add:

```sql
CREATE OR REPLACE FUNCTION reject_question_id_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.question_id IS DISTINCT FROM NEW.question_id THEN
        RAISE EXCEPTION 'original_inputs.question_id is immutable once set';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER original_inputs_question_id_immutable
BEFORE UPDATE ON original_inputs
FOR EACH ROW EXECUTE FUNCTION reject_question_id_mutation();
```

This coexists cleanly with the existing `original_inputs_enqueue_job`
trigger (different concern, different trigger).

- `submission_key` is **not globally unique** — many rows share one
  submission (one per answer). `source` and `form_key` are not columns on
  `original_inputs` (they live on `questions`), so submission retrieval
  requires a join. WP7 defines the required query shape; no additional
  index is needed beyond `idx_original_inputs_submission_key` combined
  with `idx_questions_source_form`, at this system's stated scale.

### No change to `input_embeddings` uniqueness

**Correction from v1: do not relax embedding uniqueness.** Keep:

```sql
CONSTRAINT input_embeddings_original_input_unique UNIQUE (original_input_id)
CONSTRAINT input_embeddings_segment_input_unique UNIQUE (segment_input_id)
```

unchanged. Every input and every segment has exactly one embedding, full
stop — no multiple representations, no version-compatibility filtering
needed anywhere downstream. What changes is only the *text sent to the
embedding model* (handled in WP4), not how many rows exist per input.

This also resolves a v1 self-contradiction: separate `answer-only-v1` /
`question-answer-v1` representations would have meant contextual and
generic inputs could never land in the same embedding-similarity
comparison, which conflicts directly with themes being globally scoped.
With one embedding per input, generic and contextual inputs share one
vector space by construction.

Optionally, for observability only (not used in any `WHERE` clause or
uniqueness constraint), add:

```sql
ALTER TABLE input_embeddings
    ADD COLUMN embedding_representation TEXT NOT NULL DEFAULT 'answer-only'
        CONSTRAINT input_embeddings_representation_nonempty
        CHECK (btrim(embedding_representation) <> '');
```

purely so logs and manual inspection can distinguish which rows were built
with question context. This is a plain descriptive column, not a
partitioning mechanism.

### Theme materialization tables (new — see WP6/WP7)

```sql
ALTER TABLE themes
    ADD COLUMN merged_into_id BIGINT
        REFERENCES themes (id) ON DELETE SET NULL
        CONSTRAINT themes_not_self_merged CHECK (merged_into_id <> id);

CREATE INDEX idx_themes_merged_into ON themes (merged_into_id)
    WHERE merged_into_id IS NOT NULL;

ALTER TABLE theme_suggestions
    ADD COLUMN materialized_theme_id BIGINT
        REFERENCES themes (id) ON DELETE RESTRICT,
    ADD COLUMN materialized_at TIMESTAMPTZ,
    ADD CONSTRAINT theme_suggestions_materialization_consistent
        CHECK (
            (materialized_theme_id IS NULL AND materialized_at IS NULL)
            OR
            (materialized_theme_id IS NOT NULL AND materialized_at IS NOT NULL)
        );

CREATE INDEX idx_theme_suggestions_unmaterialized
    ON theme_suggestions (id)
    WHERE materialized_at IS NULL;
```

`theme_topics` is unchanged — it is already the correct
topic-currently-belongs-to-theme table; WP6/WP7 define how it gets
populated (today nothing ever writes to it — see WP7).

`materialized_theme_id` records the theme produced by applying a suggestion.
It points to the canonical theme at materialization time. If that theme is
merged later, readers resolve it through `themes.merged_into_id`. Existing
suggestions receive `NULL` in both new columns and are deliberately treated
as pending work by WP7 rather than being silently stranded.

### Fresh-install snapshot

Update `infrastructure/postgres/init.sql` to include all of the above and
append the migration filename to the seeded `schema_migrations` rows.

### Acceptance criteria

- Migration applies cleanly on a fresh database and on top of an existing
  database through `009_*`.
- Existing generic inputs and all existing tests are unaffected.
- `questions_identity_unique` and the immutability triggers on both
  `questions` and `original_inputs.question_id` are each covered by a test
  that attempts the forbidden mutation and asserts it is rejected.
- Deleting a referenced `questions` row fails with a foreign key violation.
- `input_embeddings` still rejects a second row for the same
  `original_input_id` or `segment_input_id` — confirm no behavior change
  here versus the current schema.
- Existing `theme_suggestions` migrate with `materialized_theme_id IS NULL`
  and `materialized_at IS NULL`, and are discoverable through
  `idx_theme_suggestions_unmaterialized`.

---

## WP2 — API contract and question resolution

### Payload shape

```json
{
  "original_text": "Price",
  "source": "customer-survey",
  "submission_key": "response-4832",
  "question_context": {
    "form_key": "quarterly-survey",
    "question_key": "purchase-barrier",
    "question_version": 1,
    "question_text": "What is the biggest barrier preventing you from purchasing?"
  }
}
```

`submission_key` is top-level, not nested in `question_context` — a
submission groups multiple answers, each with its own question.

### `QuestionContext` model

- `form_key`, `question_key`, `question_text` required together.
- `question_version` optional, defaults to `1`.
- All absent → generic input, unchanged behavior.
- Partial subset present → `422`.

### Question resolution (get-or-create) — single transaction

**Correction from v1: this must be explicit.** The entire request handler —
question resolution *and* the `original_inputs` insert — runs inside one
`connection.transaction()` block, not as separate round trips. This
guarantees the input row's `question_id` FK always resolves against a
question row from the same transactional snapshot, and that a failure
anywhere in the handler rolls back both the question resolution and the
input insert together.

Within that transaction:

1. Look up `questions` by the identity tuple.
2. If found and `question_text` matches → reuse the `id`.
3. If found and `question_text` does not match → `409 Conflict` (caller
   must bump `question_version`).
4. If not found → `INSERT ... ON CONFLICT (source, form_key, question_key,
   question_version) DO NOTHING RETURNING id`; if that returns no row
   (lost the race to a concurrent request), `SELECT` the now-existing row
   instead, still inside the same transaction.
5. Insert into `original_inputs` using the resolved `question_id`.

### `submission_key` validation

- Allowed only when `question_context` is present. Otherwise `422`.

### Schema updates

- `InputCreate` gains optional `question_context: QuestionContext | None`
  and optional `submission_key: str | None`.
- `InputResponse` gains `question_id`, a resolved read-only
  `question_context` object, and `submission_key`.

### Acceptance criteria

- Existing generic-only payloads still return `201` unchanged.
- Contextual payload creates-or-reuses a `questions` row correctly.
- Mismatched `question_text` for an existing `(identity)` → `409`.
- Concurrency test: many simultaneous first-submissions of an identical new
  question create exactly one `questions` row.
- A test asserts that an insert failure after question resolution (e.g. a
  constraint violation on `original_inputs`) leaves no `questions` row
  behind that wasn't already committed independently — i.e. the
  transaction boundary is real, not just documented.
- `submission_key` without `question_context` → `422`. Partial
  `question_context` → `422`.

---

## WP3 — Question-aware eligibility and segmentation

Unchanged from v1:

- Join `questions` via `question_id` when loading the row to process.
- Move the LLM call to the structured-JSON pattern already used in
  `topics.py`/`themes.py`: `{"answer_text": ..., "question_text": ...}`,
  omitting `question_text` for generic inputs rather than sending `null`.
- Update `SYSTEM_PROMPT`: a short or closed-form answer is meaningful when
  it directly addresses the question. Spam/blank/non-responsive text stays
  ineligible regardless of question context.
- Segments contain only answer content — never inject `question_text` into
  `segment_text`.

### Acceptance criteria

- "No" is eligible answering a yes/no question; "Price" is eligible
  answering a purchase-barrier question.
- Blank/spam/non-responsive answers remain ineligible with question context
  present.
- All existing generic-input tests pass unmodified.

---

## WP4 — Context-aware embedding text

Simplified from v1 given WP1's correction (one embedding per input, always):

- Add a shared helper:

```python
def build_embedding_input(*, answer_text: str, question_text: str | None) -> str:
    if question_text is None:
        return answer_text
    return f"Question: {question_text}\nAnswer: {answer_text}"
```

- `embeddings.py` uses this for the original input and every segment,
  passing the parent input's `question_text` (joined via `question_id`) to
  each segment. Segments inherit their parent's question context.
- Optionally set `embedding_representation` (`"answer-only"` or
  `"question-answer"`) on the single `input_embeddings` row, purely for
  observability, per WP1.
- No versioning, no backfill, no compatibility filtering — there is nothing
  to reconcile, since each input has exactly one embedding, computed once,
  from whatever context it had at creation time.

### Acceptance criteria

- A contextual input and a generic input with identical `original_text`
  produce different embedding vectors.
- Two different questions both answered "No" no longer produce identical
  embedding input text.
- `original_text` and `segment_text` remain byte-for-byte unchanged in
  their tables.

---

## WP5 — Question-aware topic assignment

- Target-building loop in `topics.py` includes `question_text` on every
  target (original and segment), via the parent's `question_id`.
- `_similar_segments` tiering:
  1. For a contextual target, first query restricted to evidence whose
     parent `original_inputs.question_id` matches the target's
     `question_id`.
  2. If tier 1 returns fewer than `similar_limit` rows, **and the target's
     answer is not low-information** (see shared helper below), fall back
     to the current global query to fill the remainder.
  3. **Correction from v1**: if the target's answer *is* low-information,
     do **not** fall back to global evidence at all — use only
     same-question evidence (which may be empty; the LLM still has
     `question_text` to work from). This directly fixes the v1
     acceptance-criterion contradiction, where the global fallback could
     still surface unrelated-question evidence for exactly the ambiguous,
     easily-miscontextualized answers ("No", "Price") that most need
     protecting against cross-contamination.
  4. Generic inputs (`question_id IS NULL`) always use the global query
     only, unchanged from today.
  - Tag each evidence item `"scope": "same_question" | "global"` for the
    LLM.

### Shared low-information helper (used by WP5 and WP6 — defined once)

```python
LOW_INFO_MAX_CHARS = 15  # env: TOPIC_LOW_INFO_MAX_CHARS
LOW_INFO_CLOSED_FORM = {
    "yes", "no", "n/a", "na", "none", "maybe", "unsure", "idk",
}  # env: TOPIC_LOW_INFO_CLOSED_FORM (comma-separated override)

def is_low_information(text: str) -> bool:
    normalized = text.strip().casefold()
    if normalized in LOW_INFO_CLOSED_FORM:
        return True
    return len(text.strip()) < LOW_INFO_MAX_CHARS
```

Both thresholds are environment-configurable with the defaults above, and
this exact function is imported by both `topics.py` and `themes.py` so the
rule is defined in exactly one place.

- Update `SYSTEM_PROMPT` to instruct the model to use `question_text` for
  short/ambiguous answers and to prefer `same_question` evidence over
  `global` evidence.

### Acceptance criteria

- "Price" receives a barrier-related topic answering a purchase-barrier
  question.
- A regression test with a low-information contextual answer (e.g. "No")
  and zero same-question evidence confirms **no** global evidence is
  attached to that target — closing the v1 gap directly.
- Existing generic-input topic tests pass unmodified.

---

## WP6 — Topic-level theme inference (redesigned)

**Correction from v1, addressing the core clustering objection:** the
previous plan kept `group_related_units`'s answer-embedding
connected-components clustering unchanged, while expecting it to bridge
"Cost Barriers" and "Checkout Friction" answers into one "Purchasing"
theme. Those two answers' raw embeddings have no reason to be
similar — they're about different things at the answer level. The
mechanism that's supposed to bridge them can't do it. This package
replaces answer-level clustering with **topic-level aggregation**, since
topics (assigned in WP5) are the layer that already carries a compact,
LLM-produced semantic label — bridging *those* is a much better-posed
problem than bridging raw answer text.

### New grouping unit: topic clusters, not embedding components

Replace `group_related_units`'s graph/BFS approach with:

1. Load all lightweight `AnalysisUnit`s from `completed` inputs/segments
   with a non-null `topic`, extended to include `question_id` and
   `question_text` via a join through `original_inputs`. This membership
   query is not capped by the old `THEME_CANDIDATE_LIMIT`: a sliding window
   would cause old members to disappear, producing unstable counts and
   fingerprints. Do not load embedding vectors because theme grouping no
   longer uses them.
2. Group units by canonical topic (`topic.casefold()`), producing one
   `TopicCluster` per distinct topic string:
   - `topic_name`: canonical display name (first-seen casing).
   - `member_units`: all units under this topic.
   - `distinct_question_ids`: set of question ids represented (empty for
     purely generic members).
   - `distinct_question_texts`: their corresponding texts.
   - `rich_member_count`: count of members where
     `not is_low_information(unit.text)`.
3. A `TopicCluster` is **eligible for theme evaluation** when:
   - `rich_member_count >= THEME_MIN_RICH_UNITS` (default `2`), **or**
   - all members are low-information, but
     `len(distinct_question_ids) >= THEME_MIN_DISTINCT_QUESTIONS_LOW_INFO`
     (default `3`) — i.e. the same low-information answer recurring across
     at least three distinct questions is still allowed to surface a
     theme, but a handful of "No"s to one or two questions is not.

**This is the concrete, testable replacement for v1's underspecified
short-answer guard** — it is a counting rule over group membership, not a
graph-edge heuristic, and both thresholds are named, defaulted, and
environment-configurable.

### Stable membership and deduplication

Fingerprint the canonical topic plus the complete, ordered membership:

```text
canonical_topic
|original:12
|segment:31
|segment:44
```

Hash this stream incrementally rather than building one large string in
memory. Membership is read in `(topic, entity_type, entity_id)` order, so the
fingerprint is deterministic and changes exactly when the topic's completed
evidence membership changes. It never depends on a recent-candidate window.

Only evidence text sent to the LLM is capped. Topic counts, low-information
eligibility, distinct-question counts, and the membership fingerprint are
computed over the complete cluster. Retire `THEME_CANDIDATE_LIMIT`; replace
it with a clearly named `THEME_SAMPLE_EVIDENCE_LIMIT` (default `5`) that
controls only the prompt sample.

### LLM evidence and prompt

For each eligible `TopicCluster`, send:

```json
{
  "topic": "Cost Barriers",
  "questions": [
    {"question_text": "What is the biggest barrier preventing you from purchasing?"}
  ],
  "sample_evidence": ["Price", "Too expensive for what it offers"],
  "member_count": 14,
  "existing_themes": [...]
}
```

`sample_evidence` is capped by `THEME_SAMPLE_EVIDENCE_LIMIT`, preferring
diversity across `distinct_question_ids` when the topic spans multiple
questions.

Update `SYSTEM_PROMPT` to instruct the LLM that it is being shown a
**topic**, not a raw answer group, and should decide whether this topic
belongs to an existing theme, warrants a new theme, should be merged into
one, or should update one — using the topic name, its questions, and its
sample evidence, and that the resulting theme name must stay 1–3 words
(existing `RequiredName` length constraint already enforces the outer
bound; tighten the prompt language to state the 1–3 word target
explicitly, since "≤120 chars" alone permits much longer names than
intended).

### What no longer exists

`group_related_units`, its adjacency-graph construction, and
`_cosine_similarity`-based edge thresholds (`similarity_threshold`,
`topic_similarity_threshold`) are removed from `themes.py`. Topic-level
centroid embeddings are **not** required for this design — grouping is by
exact canonical topic string (already deduplicated case-insensitively by
`_resolve_topic` in WP5), not by embedding proximity. This is a
significant simplification versus both the current codebase and v1 of
this plan: the code that previously did BFS over a similarity graph
becomes a `GROUP BY topic` with two count-based eligibility checks.

### Acceptance criteria

- Topic-level inference is tested independently of materialization:
  "Cost Barriers" produces a decision proposing a new "Purchasing" theme
  when no suitable theme exists, while "Checkout Friction" produces a
  `reuse` decision when an existing "Purchasing" theme is supplied. WP7's
  end-to-end acceptance test verifies that the first decision is
  materialized before the second cluster is evaluated.
- Merge inference has a separate fixture containing two actual existing
  themes; it must not model topic clusters as though they were themes.
- A topic-cluster with 5 low-information members ("No") from only 2
  distinct questions is **not** eligible for theme evaluation.
- The same topic-cluster with a 3rd distinct question added becomes
  eligible.
- A topic-cluster with 2 rich (non-low-information) members and any number
  of low-information members is eligible regardless of question count.
- Adding evidence older or newer than the former candidate-window boundary
  produces the same full-membership count and a deterministic fingerprint;
  adding one genuinely new member changes that fingerprint.
- No test depends on `group_related_units`, `similarity_threshold`, or
  `topic_similarity_threshold` — they and `THEME_CANDIDATE_LIMIT` are
  removed, not merely unused.

---

## WP7 — Theme materialization: suggestions become assignments

**This directly answers the "suggestions are not assignments" gap.**
`theme_suggestions` currently accumulates decisions but nothing ever
writes to `themes` or `theme_topics` — confirmed by reading the current
`_save_suggestion`, which only inserts into `theme_suggestions`,
`theme_suggestion_existing_themes`, `theme_suggestion_topics`, and
`theme_suggestion_evidence`. `_load_existing_themes` can therefore never
find anything today; "reuse an existing theme" has never been reachable.
Migration `009_remove_theme_suggestion_review.sql` removed the human
review gate, which only makes sense if suggestions are meant to be applied
automatically — that follow-through was never added. This package adds it.

### Materialization, per `decision.action`, in the same transaction as
`_save_suggestion`

- **`new`**: insert a `themes` row (`name = proposed_name`,
  `description = proposed_description`); insert one `theme_topics` row per
  linked topic (`ON CONFLICT DO NOTHING`, allowing PostgreSQL to use the
  existing case-insensitive unique index). If a live theme with the same
  case-insensitive name was materialized by an earlier pending suggestion,
  resolve that row and apply this suggestion as an effective reuse instead
  of failing the backlog on the global name constraint; the stored
  suggestion action remains `new` as an audit record of the original
  decision.
- **`reuse`**: resolve the target theme (see canonicalization below);
  insert any new `theme_topics` links (`ON CONFLICT DO NOTHING`); touch
  `themes.updated_at`. The existing theme keeps its current name and
  description; the decision's proposed fields remain in the suggestion as
  audit context.
- **`update`**: same as `reuse`, plus overwrite
  `themes.name = proposed_name` and
  `themes.description = proposed_description` for the target theme. Validate
  the proposed name against the global case-insensitive name index before
  updating; a name belonging to an unrelated live theme is rejected rather
  than silently redirected.
- **`merge`**: canonicalize `existing_theme_ids` by always resolving each
  through `merged_into_id` to its live root first (a theme can be merged
  at most one hop deep — if a merge target is itself already merged,
  resolve to *its* root, never chain); pick the canonical theme
  deterministically as the lowest `id` among the resolved roots; for every
  other resolved root, move its `theme_topics` rows to the canonical theme
  (`INSERT ... ON CONFLICT DO NOTHING` then `DELETE` the old rows,
  respecting `idx_theme_topics_case_insensitive`); do not delete the
  merged-away `themes` rows themselves (`theme_suggestion_existing_themes`
  references them with `ON DELETE RESTRICT`, so they must remain, just
  redirected). Rename and redescribe the canonical theme using
  `proposed_name` and `proposed_description`.

  Before marking a losing root as merged, also repoint every existing alias
  whose `merged_into_id` references that losing root directly to the new
  canonical root. Then set the losing root's own `merged_into_id` to the
  canonical root. This path compression is required to preserve the
  invariant that every merged-away row points directly to a live root;
  `A → B → C` chains are never left behind.

After any action succeeds, update the suggestion with the resulting
canonical `materialized_theme_id` and `materialized_at = CURRENT_TIMESTAMP`
inside the same transaction. A failure rolls back the suggestion,
live-theme changes, topic links, and materialization marker together.

### Pending suggestions and package handoff

WP6 may create suggestions before WP7 is deployed, and suggestions from the
pre-question-context implementation may already exist. WP7 must not rely
only on `_save_suggestion` returning a newly inserted row.

Add `materialize_pending_suggestions`, which:

1. Selects suggestions where `materialized_at IS NULL` in ascending `id`
   order.
2. Reconstructs the stored decision from
   `theme_suggestions`, `theme_suggestion_existing_themes`, and
   `theme_suggestion_topics`.
3. Resolves referenced themes to their current live roots.
4. Applies the action transactionally and records
   `materialized_theme_id`/`materialized_at`.

Run this pass once when the theme worker starts, before entering the queue
loop, so deployment does not depend on a new input arriving to trigger the
backlog. Also run it at the beginning of each normal theme cycle for retry
safety. The operation is idempotent: a row with non-null `materialized_at`
is never applied again.

Within a normal cycle, materialize each newly saved suggestion before
loading existing themes for the next topic cluster. Consequently, if
"Cost Barriers" creates "Purchasing", the following "Checkout Friction"
cluster can see and reuse "Purchasing" during the same cycle.

### Topic-to-theme cardinality

Retain the existing many-to-many model deliberately: one topic may be linked
to multiple broad themes, and one theme may contain multiple topics.
Materialization adds the link selected by the decision and does not remove
other live links for that topic. `ON CONFLICT DO NOTHING` prevents only a
duplicate link to the same theme.

All APIs and SQL examples must therefore expose `themes` as a collection,
even when the common case contains one theme. No code may assume that
joining a topic through `theme_topics` returns at most one row.

### Reads

- `_load_existing_themes` adds `WHERE themes.merged_into_id IS NULL` so
  merged-away themes are never offered as reuse/merge targets again.
- A theme's *current* linked topics are always read from `theme_topics`
  directly — `theme_suggestions`/`theme_suggestion_topics` remain as an
  audit trail of how each decision was reached, not as the live-state
  source.
- Reads of `theme_suggestions.materialized_theme_id` resolve through
  `merged_into_id` in case its originally materialized theme was merged
  later.

### Resulting queryable chain

`original_inputs.topic` (or `segment_inputs.topic`) → `theme_topics.topic`
→ `theme_topics.theme_id` → `themes.name` (following `merged_into_id` if
set) gives the answer → topic → themes chain the feature is meant to
produce, e.g. `"Price" → "Cost Barriers" → ["Purchasing"]`.

### Acceptance criteria

- After a `new` decision, the topic is queryable to its theme via
  `theme_topics` — not just visible in `theme_suggestions` — and the
  suggestion records `materialized_theme_id` and `materialized_at`.
- Suggestions created before WP7 are materialized by the startup backlog
  pass without requiring a newly completed input.
- End to end within one cycle: materializing a `new` "Purchasing" decision
  for "Cost Barriers" makes that live theme available to the following
  "Checkout Friction" cluster, whose `reuse` decision links the second topic
  to the same theme.
- After a `merge` decision, both original themes' topics resolve to the
  same canonical theme, and the merged-away theme's row still exists
  (satisfying the `RESTRICT` FK) but is excluded from
  `_load_existing_themes`.
- `update` and `merge` apply the decision's proposed name and description to
  the resulting canonical theme.
- A regression test starts with `A → B`, merges `B` into `C`, and confirms
  both `A` and `B` point directly to `C`.
- Replaying materialization after success is a no-op. Concurrent attempts to
  add the same `(theme, topic)` link do not create duplicate rows, while
  links from that topic to other themes remain valid by design.

---

## WP8 — Form, question, and submission retrieval

```
GET /inputs?source=customer-survey&form_key=quarterly-survey
GET /inputs?source=customer-survey&form_key=quarterly-survey&question_key=purchase-barrier[&question_version=1]
GET /inputs?source=customer-survey&form_key=quarterly-survey&submission_key=response-4832
```

**Correction from v1 (two points):**

- `question_key` alone is ambiguous across sources/forms/versions.
  `source` and `form_key` are **required** whenever `question_key` or
  `submission_key` is supplied; supplying either without both returns
  `422`. `question_version` remains optional and, when omitted, matches
  all versions of that question (using the identity index's leftmost
  prefix, per WP1 — no extra index needed).
- `submission_key` is likewise required to be paired with `source` and
  `form_key`, since it is not globally unique.

- Each result includes the resolved `question_context` and existing fields
  (`topic`, `status`, etc.). Include resolved `themes` as an array (via the
  WP7 chain), since the live relationship is intentionally many-to-many.
  Deduplicate canonical themes after following `merged_into_id`.
- Offset/limit pagination, validated and bounded — sufficient for this
  system's stated low-throughput scale; document the choice rather than
  building cursor pagination speculatively.
- Optional stretch, not required for this package: `GET
  /theme-suggestions` surfacing contributing forms/questions per
  suggestion via the WP6/WP7 evidence links.

### Testing correction from v1

**Do not assert index usage via `EXPLAIN` on small fixtures** — the
planner may correctly choose a sequential scan on a handful of rows, and a
test asserting otherwise is testing planner heuristics, not correctness.
Instead:
- Assert query *correctness* (right rows returned) against small fixtures.
- Assert the *indexes themselves exist* via a schema/metadata query
  (`pg_indexes` or equivalent), independent of whether the planner uses
  them for a tiny fixture.
- If planner behavior genuinely needs verification, do it in a separate,
  explicitly-labeled performance test against a realistically sized seeded
  fixture (thousands of rows), not the standard unit-test suite.

### Acceptance criteria

- All answers belonging to one `(source, form_key, submission_key)` are
  reconstructed via a single request.
- An answer whose topic belongs to multiple themes returns all canonical
  themes without duplicate merged aliases.
- `question_key`/`submission_key` without both `source` and `form_key`
  return `422`.
- Pagination parameters are validated and bounded.
- Required indexes are present in the schema (asserted via metadata query,
  not planner behavior).

---

## WP9 — Testing and documentation

- Fixtures covering: short contextual answer, long contextual answer,
  identical answer text to two different questions, related answers to the
  same question, multiple answers within one submission, and a fully
  generic input — run through the full pipeline (eligibility → embedding →
  topic → theme → materialization).
- Concurrency test for question get-or-create (WP2).
- Conflict test: resubmitting an existing identity with different
  `question_text` returns `409`.
- The worked example, end to end: two differently-worded questions'
  answers get topics like "Cost Barriers" / "Checkout Friction", and
  materialize into topics linked under one "Purchasing" theme, verifiable
  by querying `theme_topics` directly — not just inspecting
  `theme_suggestions`.
- A separate merge fixture verifies proposed-name application and path
  compression when aliases already point at a losing root.
- Extend the interactive manual test script with contextual sample
  payloads for each fixture above.
- Add example SQL queries for: answers by question, answers by submission,
  pending/materialized suggestions, and the full answer → topic → themes
  chain (including merged themes, following `merged_into_id`).
- Update `README.md` and `docs/architecture.md`: the `questions` table,
  the topic/theme granularity distinction, the removal of
  embedding-similarity-based theme clustering in favor of topic-level
  aggregation, and the theme materialization/merge semantics.

### Acceptance criteria

- Full test suite passes, including new fixtures.
- Manual test runner demonstrates generic and question-based processing
  end to end, including a materialized theme.
- Database inspection queries clearly show form → question → submission →
  answer → topic → themes relationships, with merges resolved.

---

## Recommended execution order

WP1 → WP2 → WP3 → WP4 → WP5 → WP6 → WP7 → WP8 → WP9

WP6 and WP7 are now the highest-risk packages, not WP1 — WP1 is
comparatively simple in this revision (no versioning scheme to design).
WP6 replaces a core algorithm rather than extending it, and WP7 introduces
merge semantics with a foreign-key constraint (`RESTRICT`) that must be
respected without deleting data. Review WP6/WP7's design against a couple
of hand-worked examples (including at least one merge) before
implementation starts, since a wrong call on merge canonicalization is
expensive to unwind once theme data exists.
