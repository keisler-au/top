BEGIN;

-- PTR-1 requires real question context.  Historical wording cannot be safely
-- reconstructed, so an installation with unresolved rows must stop here and
-- be audited before this migration is retried.
DO $$
DECLARE
    unresolved BIGINT;
BEGIN
    SELECT count(*) INTO unresolved
    FROM original_inputs
    WHERE question_id IS NULL;

    IF unresolved <> 0 THEN
        RAISE EXCEPTION
            'PTR-1 requires question context; % original_inputs rows have no question_id',
            unresolved;
    END IF;
END;
$$;

ALTER TABLE original_inputs
    ALTER COLUMN question_id SET NOT NULL;

-- Preserve the exact structured eligibility/segmentation decision that owns
-- every segment.  Rows processed before this audit boundary receive explicit
-- legacy provenance rather than an invented model or prompt identity.
CREATE TABLE input_preparation_decisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    original_input_id BIGINT NOT NULL UNIQUE
        REFERENCES original_inputs (id) ON DELETE RESTRICT,
    worker_job_id BIGINT UNIQUE
        REFERENCES worker_jobs (id) ON DELETE RESTRICT,
    eligible BOOLEAN NOT NULL,
    segments JSONB NOT NULL
        CHECK (jsonb_typeof(segments) = 'array'),
    model TEXT NOT NULL CHECK (btrim(model) <> ''),
    prompt_version TEXT NOT NULL CHECK (btrim(prompt_version) <> ''),
    decision_source TEXT NOT NULL
        CHECK (decision_source IN ('model', 'legacy-backfill')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, original_input_id),
    CHECK (eligible OR segments = '[]'::jsonb)
);

INSERT INTO input_preparation_decisions (
    original_input_id,
    eligible,
    segments,
    model,
    prompt_version,
    decision_source
)
SELECT
    inputs.id,
    inputs.status <> 'ineligible',
    COALESCE(
        (
            SELECT jsonb_agg(segments.segment_text ORDER BY segments.segment_order)
            FROM segment_inputs AS segments
            WHERE segments.original_input_id = inputs.id
        ),
        '[]'::jsonb
    ),
    'legacy-unrecorded',
    'legacy-unrecorded',
    'legacy-backfill'
FROM original_inputs AS inputs
WHERE inputs.status <> 'new';

ALTER TABLE segment_inputs
    ADD COLUMN preparation_decision_id BIGINT;

UPDATE segment_inputs AS segments
SET preparation_decision_id = decisions.id
FROM input_preparation_decisions AS decisions
WHERE decisions.original_input_id = segments.original_input_id;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM segment_inputs WHERE preparation_decision_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'PTR-1 cannot link every historical segment to a preparation decision';
    END IF;
END;
$$;

ALTER TABLE segment_inputs
    ALTER COLUMN preparation_decision_id SET NOT NULL,
    ADD CONSTRAINT segment_inputs_preparation_decision_fk
        FOREIGN KEY (preparation_decision_id, original_input_id)
        REFERENCES input_preparation_decisions (id, original_input_id)
        ON DELETE RESTRICT;

CREATE OR REPLACE FUNCTION reject_input_preparation_decision_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'input preparation decisions are immutable';
END;
$$;

CREATE TRIGGER input_preparation_decisions_immutable
BEFORE UPDATE OR DELETE ON input_preparation_decisions
FOR EACH ROW
EXECUTE FUNCTION reject_input_preparation_decision_mutation();

-- Existing frozen plans remain readable.  New partial-topic-policy/v1 plans
-- identify their immutable question scope and persist their gate result and
-- packet metadata alongside the calibrated diagnostics JSON.
ALTER TABLE taxonomy_cluster_candidates
    DROP CONSTRAINT taxonomy_cluster_candidates_taxonomy_run_id_algorithm_label_key,
    ADD COLUMN question_id BIGINT REFERENCES questions (id) ON DELETE RESTRICT,
    ADD COLUMN policy_version TEXT NOT NULL DEFAULT 'legacy-cluster-policy'
        CHECK (btrim(policy_version) <> ''),
    ADD COLUMN eligible BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN failure_reasons TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN packet_serialized_bytes INTEGER
        CHECK (packet_serialized_bytes IS NULL OR packet_serialized_bytes >= 2),
    ADD COLUMN unique_original_count INTEGER
        CHECK (unique_original_count IS NULL OR unique_original_count >= 1),
    ADD CONSTRAINT taxonomy_cluster_policy_question_required CHECK (
        policy_version <> 'partial-topic-policy/v1' OR question_id IS NOT NULL
    ),
    ADD CONSTRAINT taxonomy_cluster_eligibility_consistent CHECK (
        eligible = (cardinality(failure_reasons) = 0)
    );

CREATE UNIQUE INDEX taxonomy_cluster_candidates_question_label_unique
    ON taxonomy_cluster_candidates (taxonomy_run_id, question_id, algorithm_label)
    WHERE question_id IS NOT NULL;

ALTER TABLE taxonomy_cluster_representatives
    DROP CONSTRAINT taxonomy_cluster_representatives_selection_kind_check,
    ADD CONSTRAINT taxonomy_cluster_representatives_selection_kind_check
        CHECK (selection_kind IN ('all', 'central', 'diverse'));

ALTER TABLE topic_representative_evidence
    DROP CONSTRAINT topic_representative_evidence_selection_kind_check,
    ADD CONSTRAINT topic_representative_evidence_selection_kind_check
        CHECK (selection_kind IN ('all', 'central', 'diverse', 'manual'));

COMMIT;
