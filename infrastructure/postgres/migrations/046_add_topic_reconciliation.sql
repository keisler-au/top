BEGIN;

-- PTR-3 inserts canonical topic reconciliation between provisional naming and
-- theme inference. Existing completed runs retain their historical canonical
-- topics; active candidates receive the new stage without rewriting evidence.
ALTER TABLE taxonomy_run_stages
    DROP CONSTRAINT taxonomy_run_stages_stage_check;
ALTER TABLE taxonomy_run_stages
    ADD CONSTRAINT taxonomy_run_stages_stage_check CHECK (stage IN (
        'snapshot', 'clustering', 'topic_naming', 'topic_reconciliation',
        'theme_inference', 'theme_reconciliation', 'quality',
        'ready_for_publication'
    ));

INSERT INTO taxonomy_run_stages(
    taxonomy_run_id, stage, attempt, status, completed_at, error_class,
    stage_output_sha256
)
SELECT run.id, 'topic_reconciliation',
       CASE WHEN run.status IN ('ready_for_review', 'published', 'superseded', 'rejected', 'failed') THEN 1 ELSE 0 END,
       CASE
           WHEN run.status IN ('ready_for_review', 'published', 'superseded') THEN 'completed'
           WHEN run.status = 'rejected' THEN 'cancelled'
           WHEN run.status = 'failed' THEN 'failed'
           ELSE 'pending'
       END,
       CASE WHEN run.status IN ('ready_for_review', 'published', 'superseded')
            THEN COALESCE(run.completed_at, run.updated_at) END,
       CASE WHEN run.status = 'failed' THEN 'legacy_state' END,
       CASE WHEN run.status IN ('ready_for_review', 'published', 'superseded')
            THEN repeat('0', 64) END
FROM taxonomy_runs AS run
ON CONFLICT (taxonomy_run_id, stage) DO NOTHING;

ALTER TABLE taxonomy_model_requests
    DROP CONSTRAINT taxonomy_model_requests_stage_check;
ALTER TABLE taxonomy_model_requests
    ADD CONSTRAINT taxonomy_model_requests_stage_check CHECK (
        stage IN ('topic_naming', 'topic_reconciliation', 'theme_inference')
    );

ALTER TABLE taxonomy_model_requests
    ADD CONSTRAINT taxonomy_model_requests_run_id_unique
        UNIQUE (taxonomy_run_id, id);

CREATE TABLE taxonomy_topic_reconciliation_decisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs(id) ON DELETE RESTRICT,
    packet_key TEXT NOT NULL CHECK (btrim(packet_key) <> '' AND char_length(packet_key) <= 500),
    decision_kind TEXT NOT NULL CHECK (decision_kind IN ('model', 'isolated')),
    taxonomy_model_request_id BIGINT REFERENCES taxonomy_model_requests(id) ON DELETE RESTRICT,
    policy_version TEXT NOT NULL CHECK (btrim(policy_version) <> ''),
    provisional_topic_ids BIGINT[] NOT NULL CHECK (cardinality(provisional_topic_ids) > 0),
    decision JSONB NOT NULL CHECK (jsonb_typeof(decision) = 'object'),
    validation_errors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    accepted BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, id),
    UNIQUE (taxonomy_run_id, packet_key),
    UNIQUE (taxonomy_model_request_id),
    FOREIGN KEY (taxonomy_run_id, taxonomy_model_request_id)
        REFERENCES taxonomy_model_requests(taxonomy_run_id, id) ON DELETE RESTRICT,
    CHECK (accepted = (cardinality(validation_errors) = 0)),
    CHECK ((decision_kind = 'model') = (taxonomy_model_request_id IS NOT NULL))
);

CREATE TABLE taxonomy_canonical_topic_antecedents (
    taxonomy_run_id BIGINT NOT NULL,
    topic_revision_id BIGINT NOT NULL,
    provisional_topic_id BIGINT NOT NULL,
    reconciliation_decision_id BIGINT NOT NULL,
    relationship TEXT NOT NULL CHECK (relationship IN ('singleton', 'equivalent')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (taxonomy_run_id, topic_revision_id, provisional_topic_id),
    UNIQUE (taxonomy_run_id, provisional_topic_id),
    FOREIGN KEY (taxonomy_run_id, topic_revision_id)
        REFERENCES topic_revisions(taxonomy_run_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (taxonomy_run_id, provisional_topic_id)
        REFERENCES taxonomy_provisional_topics(taxonomy_run_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (taxonomy_run_id, reconciliation_decision_id)
        REFERENCES taxonomy_topic_reconciliation_decisions(taxonomy_run_id, id) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION validate_canonical_topic_membership()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- Historical/manual compatibility runs predate provisional topics. Apply
    -- the stronger source rule only to candidates using the PTR-3 boundary.
    IF NOT EXISTS (
        SELECT 1 FROM taxonomy_provisional_topics
        WHERE taxonomy_run_id = NEW.taxonomy_run_id
    ) THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM taxonomy_canonical_topic_antecedents AS antecedent
        JOIN taxonomy_provisional_topics AS provisional
          ON provisional.taxonomy_run_id = antecedent.taxonomy_run_id
         AND provisional.id = antecedent.provisional_topic_id
        JOIN taxonomy_cluster_memberships AS membership
          ON membership.taxonomy_run_id = provisional.taxonomy_run_id
         AND membership.cluster_candidate_id = provisional.cluster_candidate_id
         AND membership.evidence_id = NEW.evidence_id
         AND membership.decision = 'clustered'
        WHERE antecedent.taxonomy_run_id = NEW.taxonomy_run_id
          AND antecedent.topic_revision_id = NEW.topic_revision_id
    ) THEN
        RAISE EXCEPTION 'canonical topic membership requires an antecedent cluster membership';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER topic_memberships_canonical_source
BEFORE INSERT ON topic_memberships
FOR EACH ROW EXECUTE FUNCTION validate_canonical_topic_membership();

CREATE TRIGGER topic_reconciliation_decisions_guard
BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_topic_reconciliation_decisions
FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();

CREATE TRIGGER canonical_topic_antecedents_guard
BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_canonical_topic_antecedents
FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();

CREATE OR REPLACE FUNCTION validate_canonical_topic_antecedent()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM taxonomy_topic_reconciliation_decisions AS decision
        WHERE decision.taxonomy_run_id=NEW.taxonomy_run_id
          AND decision.id=NEW.reconciliation_decision_id AND decision.accepted
          AND NEW.provisional_topic_id=ANY(decision.provisional_topic_ids)
    ) THEN
        RAISE EXCEPTION 'canonical antecedent requires an accepted decision for its provisional topic';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER canonical_topic_antecedent_valid BEFORE INSERT
ON taxonomy_canonical_topic_antecedents
FOR EACH ROW EXECUTE FUNCTION validate_canonical_topic_antecedent();

COMMIT;
