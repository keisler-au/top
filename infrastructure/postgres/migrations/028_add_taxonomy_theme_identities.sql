BEGIN;

-- Candidate themes are run-local audit records.  These tables are the stable
-- public identity layer: a revision belongs to exactly one immutable run and
-- a lineage record is the only way an old identity can resolve to a new one.
CREATE TABLE theme_identities (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_in_run_id BIGINT NOT NULL REFERENCES taxonomy_runs(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, created_in_run_id)
);

CREATE TABLE theme_revisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    theme_id BIGINT NOT NULL REFERENCES theme_identities(id) ON DELETE RESTRICT,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs(id) ON DELETE RESTRICT,
    reconciled_theme_id BIGINT NOT NULL,
    name TEXT NOT NULL CHECK (btrim(name) <> '' AND char_length(name) <= 120),
    normalized_name TEXT NOT NULL CHECK (normalized_name = lower(btrim(name))),
    description TEXT NOT NULL CHECK (btrim(description) <> '' AND char_length(description) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, id),
    UNIQUE (taxonomy_run_id, theme_id),
    UNIQUE (taxonomy_run_id, reconciled_theme_id),
    FOREIGN KEY (taxonomy_run_id, reconciled_theme_id)
        REFERENCES taxonomy_reconciled_themes(taxonomy_run_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_theme_revisions_run_theme ON theme_revisions(taxonomy_run_id, theme_id);

CREATE TABLE theme_revision_topics (
    taxonomy_run_id BIGINT NOT NULL,
    theme_revision_id BIGINT NOT NULL,
    topic_revision_id BIGINT NOT NULL,
    PRIMARY KEY (taxonomy_run_id, theme_revision_id, topic_revision_id),
    FOREIGN KEY (taxonomy_run_id, theme_revision_id)
        REFERENCES theme_revisions(taxonomy_run_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (taxonomy_run_id, topic_revision_id)
        REFERENCES topic_revisions(taxonomy_run_id, id) ON DELETE RESTRICT
);

CREATE TABLE theme_aliases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    theme_id BIGINT NOT NULL REFERENCES theme_identities(id) ON DELETE RESTRICT,
    alias TEXT NOT NULL CHECK (btrim(alias) <> '' AND char_length(alias) <= 120),
    normalized_alias TEXT NOT NULL CHECK (normalized_alias = lower(btrim(alias))),
    created_in_run_id BIGINT NOT NULL REFERENCES taxonomy_runs(id) ON DELETE RESTRICT,
    retired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (theme_id, normalized_alias)
);
CREATE INDEX idx_theme_aliases_active_name ON theme_aliases(normalized_alias) WHERE retired_at IS NULL;

CREATE TABLE theme_lineage (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs(id) ON DELETE RESTRICT,
    predecessor_theme_id BIGINT REFERENCES theme_identities(id) ON DELETE RESTRICT,
    successor_theme_id BIGINT REFERENCES theme_identities(id) ON DELETE RESTRICT,
    relationship TEXT NOT NULL CHECK (relationship IN ('new', 'continuation', 'rename', 'split', 'merge', 'retired')),
    rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((relationship = 'new' AND predecessor_theme_id IS NULL AND successor_theme_id IS NOT NULL)
        OR (relationship = 'retired' AND predecessor_theme_id IS NOT NULL AND successor_theme_id IS NULL)
        OR (relationship IN ('continuation', 'rename', 'split', 'merge') AND predecessor_theme_id IS NOT NULL AND successor_theme_id IS NOT NULL)),
    UNIQUE (taxonomy_run_id, predecessor_theme_id, successor_theme_id, relationship)
);
CREATE INDEX idx_theme_lineage_predecessor ON theme_lineage(predecessor_theme_id, taxonomy_run_id);
CREATE OR REPLACE FUNCTION reject_theme_identity_mutation() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'theme identity, revision, and lineage records are immutable'; END; $$;
CREATE TRIGGER theme_revisions_immutable BEFORE UPDATE OR DELETE ON theme_revisions FOR EACH ROW EXECUTE FUNCTION reject_theme_identity_mutation();
CREATE TRIGGER theme_revision_topics_immutable BEFORE UPDATE OR DELETE ON theme_revision_topics FOR EACH ROW EXECUTE FUNCTION reject_theme_identity_mutation();
CREATE TRIGGER theme_lineage_immutable BEFORE UPDATE OR DELETE ON theme_lineage FOR EACH ROW EXECUTE FUNCTION reject_theme_identity_mutation();

-- The reconciliation layer is mandatory: raw candidate rows are never
-- materialised directly.  Calling this more than once is safe and cannot
-- rewrite an earlier revision.
CREATE OR REPLACE FUNCTION materialize_taxonomy_theme_revisions(candidate_run_id BIGINT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE candidate taxonomy_runs;
BEGIN
    SELECT * INTO candidate FROM taxonomy_runs WHERE id = candidate_run_id FOR UPDATE;
    IF NOT FOUND OR candidate.status NOT IN ('ready_for_review', 'published') THEN
        RAISE EXCEPTION 'taxonomy run is not ready for theme materialization';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM taxonomy_reconciled_themes WHERE taxonomy_run_id = candidate_run_id) THEN
        RAISE EXCEPTION 'taxonomy run has no reconciled themes';
    END IF;

    INSERT INTO theme_identities(created_in_run_id)
    SELECT candidate_run_id
    FROM taxonomy_reconciled_themes reconciled
    WHERE reconciled.taxonomy_run_id = candidate_run_id
      AND NOT EXISTS (SELECT 1 FROM theme_revisions revisions WHERE revisions.taxonomy_run_id = candidate_run_id AND revisions.reconciled_theme_id = reconciled.id);

    -- Pair newly-created identities to unmaterialised reconciled themes in a
    -- deterministic order.  Existing revisions make this operation idempotent.
    WITH missing AS (
        SELECT reconciled.id, row_number() OVER (ORDER BY reconciled.id) AS ordinal
        FROM taxonomy_reconciled_themes reconciled
        WHERE reconciled.taxonomy_run_id = candidate_run_id
          AND NOT EXISTS (SELECT 1 FROM theme_revisions revisions WHERE revisions.taxonomy_run_id = candidate_run_id AND revisions.reconciled_theme_id = reconciled.id)
    ), identities AS (
        SELECT identities.id, row_number() OVER (ORDER BY identities.id) AS ordinal
        FROM theme_identities identities WHERE identities.created_in_run_id = candidate_run_id
          AND NOT EXISTS (SELECT 1 FROM theme_revisions revisions WHERE revisions.theme_id = identities.id)
    )
    INSERT INTO theme_revisions(theme_id, taxonomy_run_id, reconciled_theme_id, name, normalized_name, description)
    SELECT identities.id, candidate_run_id, missing.id, themes.name, lower(btrim(themes.name)), themes.description
    FROM missing JOIN identities USING (ordinal)
    JOIN taxonomy_reconciled_themes reconciled ON reconciled.id = missing.id
    JOIN taxonomy_candidate_themes themes ON themes.id = reconciled.canonical_candidate_theme_id;

    INSERT INTO theme_revision_topics(taxonomy_run_id, theme_revision_id, topic_revision_id)
    SELECT candidate_run_id, revisions.id, links.topic_revision_id
    FROM theme_revisions revisions
    JOIN taxonomy_reconciled_themes reconciled ON reconciled.id = revisions.reconciled_theme_id
    JOIN taxonomy_reconciled_theme_antecedents antecedents ON antecedents.reconciled_theme_id = reconciled.id
    JOIN taxonomy_candidate_theme_topics links ON links.taxonomy_run_id = candidate_run_id AND links.candidate_theme_id = antecedents.candidate_theme_id
    WHERE revisions.taxonomy_run_id = candidate_run_id
    ON CONFLICT DO NOTHING;

    INSERT INTO theme_aliases(theme_id, alias, normalized_alias, created_in_run_id)
    SELECT theme_id, name, normalized_name, candidate_run_id FROM theme_revisions
    WHERE taxonomy_run_id = candidate_run_id ON CONFLICT DO NOTHING;
    INSERT INTO theme_lineage(taxonomy_run_id, predecessor_theme_id, successor_theme_id, relationship)
    SELECT candidate_run_id, NULL, theme_id, 'new' FROM theme_revisions
    WHERE taxonomy_run_id = candidate_run_id ON CONFLICT DO NOTHING;
END;
$$;

-- Resolve a stable numeric identity through a published run's lineage.  More
-- than one successor deliberately reports ambiguity instead of guessing.
CREATE OR REPLACE FUNCTION resolve_published_theme_id(requested_theme_id BIGINT)
RETURNS TABLE(theme_id BIGINT, resolution TEXT) LANGUAGE sql STABLE AS $$
    WITH published AS (SELECT id FROM taxonomy_runs WHERE status = 'published'),
    direct AS (SELECT revisions.theme_id FROM theme_revisions revisions JOIN published ON published.id = revisions.taxonomy_run_id WHERE revisions.theme_id = requested_theme_id),
    successors AS (SELECT lineage.successor_theme_id AS theme_id FROM theme_lineage lineage JOIN published ON published.id = lineage.taxonomy_run_id WHERE lineage.predecessor_theme_id = requested_theme_id AND lineage.successor_theme_id IS NOT NULL),
    choices AS (SELECT theme_id FROM direct UNION SELECT theme_id FROM successors)
    SELECT min(theme_id), CASE WHEN count(*) = 1 THEN 'resolved' ELSE 'ambiguous' END FROM choices HAVING count(*) > 0;
$$;

-- Deterministic cross-run identity matching. Exact stable-topic-set matches
-- retain identity (and distinguish rename); overlap-only matches create new
-- identities and record split/merge lineage rather than guessing continuity.
CREATE OR REPLACE FUNCTION materialize_taxonomy_theme_revisions(candidate_run_id BIGINT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE candidate taxonomy_runs; prior_run_id BIGINT; reconciled RECORD;
        candidate_topics BIGINT[]; matched_ids BIGINT[]; assigned_theme_id BIGINT;
        prior RECORD; current RECORD; predecessor_count INTEGER; successor_count INTEGER;
BEGIN
    SELECT * INTO candidate FROM taxonomy_runs WHERE id=candidate_run_id FOR UPDATE;
    IF NOT FOUND OR candidate.status NOT IN ('ready_for_review','published') THEN RAISE EXCEPTION 'taxonomy run is not ready for theme materialization'; END IF;
    IF NOT EXISTS (SELECT 1 FROM taxonomy_reconciled_themes WHERE taxonomy_run_id=candidate_run_id) THEN RAISE EXCEPTION 'taxonomy run has no reconciled themes'; END IF;
    SELECT id INTO prior_run_id FROM taxonomy_runs WHERE status='published' AND id <> candidate_run_id;
    FOR reconciled IN SELECT * FROM taxonomy_reconciled_themes WHERE taxonomy_run_id=candidate_run_id ORDER BY id LOOP
        IF EXISTS (SELECT 1 FROM theme_revisions WHERE taxonomy_run_id=candidate_run_id AND reconciled_theme_id=reconciled.id) THEN CONTINUE; END IF;
        SELECT array_agg(DISTINCT revisions.topic_id ORDER BY revisions.topic_id) INTO candidate_topics
        FROM taxonomy_reconciled_theme_antecedents antecedents
        JOIN taxonomy_candidate_theme_topics links ON links.taxonomy_run_id=candidate_run_id AND links.candidate_theme_id=antecedents.candidate_theme_id
        JOIN topic_revisions revisions ON revisions.id=links.topic_revision_id AND revisions.taxonomy_run_id=candidate_run_id
        WHERE antecedents.taxonomy_run_id=candidate_run_id AND antecedents.reconciled_theme_id=reconciled.id;
        SELECT array_agg(theme_id ORDER BY theme_id) INTO matched_ids FROM (
            SELECT revisions.theme_id FROM theme_revisions revisions
            JOIN theme_revision_topics links ON links.taxonomy_run_id=revisions.taxonomy_run_id AND links.theme_revision_id=revisions.id
            JOIN topic_revisions topics ON topics.id=links.topic_revision_id AND topics.taxonomy_run_id=links.taxonomy_run_id
            WHERE revisions.taxonomy_run_id=prior_run_id GROUP BY revisions.theme_id
            HAVING array_agg(DISTINCT topics.topic_id ORDER BY topics.topic_id)=candidate_topics
        ) matches;
        IF coalesce(array_length(matched_ids,1),0)=1 THEN assigned_theme_id:=matched_ids[1]; ELSE INSERT INTO theme_identities(created_in_run_id) VALUES(candidate_run_id) RETURNING id INTO assigned_theme_id; END IF;
        INSERT INTO theme_revisions(theme_id,taxonomy_run_id,reconciled_theme_id,name,normalized_name,description)
        SELECT assigned_theme_id,candidate_run_id,reconciled.id,themes.name,lower(btrim(themes.name)),themes.description FROM taxonomy_candidate_themes themes WHERE themes.id=reconciled.canonical_candidate_theme_id;
    END LOOP;
    INSERT INTO theme_revision_topics(taxonomy_run_id,theme_revision_id,topic_revision_id)
    SELECT candidate_run_id,revisions.id,links.topic_revision_id FROM theme_revisions revisions
    JOIN taxonomy_reconciled_theme_antecedents antecedents ON antecedents.taxonomy_run_id=candidate_run_id AND antecedents.reconciled_theme_id=revisions.reconciled_theme_id
    JOIN taxonomy_candidate_theme_topics links ON links.taxonomy_run_id=candidate_run_id AND links.candidate_theme_id=antecedents.candidate_theme_id
    WHERE revisions.taxonomy_run_id=candidate_run_id ON CONFLICT DO NOTHING;
    INSERT INTO theme_aliases(theme_id,alias,normalized_alias,created_in_run_id) SELECT theme_id,name,normalized_name,candidate_run_id FROM theme_revisions WHERE taxonomy_run_id=candidate_run_id ON CONFLICT DO NOTHING;
    IF prior_run_id IS NULL THEN INSERT INTO theme_lineage(taxonomy_run_id,predecessor_theme_id,successor_theme_id,relationship) SELECT candidate_run_id,NULL,theme_id,'new' FROM theme_revisions WHERE taxonomy_run_id=candidate_run_id ON CONFLICT DO NOTHING; RETURN; END IF;
    FOR current IN SELECT * FROM theme_revisions WHERE taxonomy_run_id=candidate_run_id LOOP
      FOR prior IN SELECT * FROM theme_revisions WHERE taxonomy_run_id=prior_run_id LOOP
        IF EXISTS (SELECT 1 FROM theme_revision_topics a JOIN topic_revisions at ON at.id=a.topic_revision_id JOIN theme_revision_topics b ON TRUE JOIN topic_revisions bt ON bt.id=b.topic_revision_id WHERE a.taxonomy_run_id=prior_run_id AND a.theme_revision_id=prior.id AND b.taxonomy_run_id=candidate_run_id AND b.theme_revision_id=current.id AND at.topic_id=bt.topic_id) THEN
          SELECT count(*) INTO successor_count FROM theme_revisions x WHERE x.taxonomy_run_id=candidate_run_id AND EXISTS (SELECT 1 FROM theme_revision_topics a JOIN topic_revisions at ON at.id=a.topic_revision_id JOIN theme_revision_topics b ON TRUE JOIN topic_revisions bt ON bt.id=b.topic_revision_id WHERE a.taxonomy_run_id=prior_run_id AND a.theme_revision_id=prior.id AND b.taxonomy_run_id=candidate_run_id AND b.theme_revision_id=x.id AND at.topic_id=bt.topic_id);
          SELECT count(*) INTO predecessor_count FROM theme_revisions x WHERE x.taxonomy_run_id=prior_run_id AND EXISTS (SELECT 1 FROM theme_revision_topics a JOIN topic_revisions at ON at.id=a.topic_revision_id JOIN theme_revision_topics b ON TRUE JOIN topic_revisions bt ON bt.id=b.topic_revision_id WHERE a.taxonomy_run_id=prior_run_id AND a.theme_revision_id=x.id AND b.taxonomy_run_id=candidate_run_id AND b.theme_revision_id=current.id AND at.topic_id=bt.topic_id);
          INSERT INTO theme_lineage(taxonomy_run_id,predecessor_theme_id,successor_theme_id,relationship) VALUES(candidate_run_id,prior.theme_id,current.theme_id,CASE WHEN prior.theme_id=current.theme_id AND prior.normalized_name=current.normalized_name THEN 'continuation' WHEN prior.theme_id=current.theme_id THEN 'rename' WHEN successor_count>1 THEN 'split' WHEN predecessor_count>1 THEN 'merge' ELSE 'rename' END) ON CONFLICT DO NOTHING;
        END IF;
      END LOOP;
    END LOOP;
    INSERT INTO theme_lineage(taxonomy_run_id,predecessor_theme_id,successor_theme_id,relationship) SELECT candidate_run_id,NULL,c.theme_id,'new' FROM theme_revisions c WHERE c.taxonomy_run_id=candidate_run_id AND NOT EXISTS(SELECT 1 FROM theme_lineage l WHERE l.taxonomy_run_id=candidate_run_id AND l.successor_theme_id=c.theme_id) ON CONFLICT DO NOTHING;
    INSERT INTO theme_lineage(taxonomy_run_id,predecessor_theme_id,successor_theme_id,relationship) SELECT candidate_run_id,p.theme_id,NULL,'retired' FROM theme_revisions p WHERE p.taxonomy_run_id=prior_run_id AND NOT EXISTS(SELECT 1 FROM theme_lineage l WHERE l.taxonomy_run_id=candidate_run_id AND l.predecessor_theme_id=p.theme_id) ON CONFLICT DO NOTHING;
END; $$;

-- Publication preparation materialises the stable reader projection before
-- the run can become visible to any reader.
CREATE OR REPLACE FUNCTION publish_taxonomy_run(candidate_run_id BIGINT, expected_updated_at TIMESTAMPTZ, operator_name TEXT, operator_note TEXT DEFAULT NULL)
RETURNS taxonomy_runs LANGUAGE plpgsql AS $$
DECLARE published taxonomy_runs;
BEGIN
    PERFORM materialize_taxonomy_theme_revisions(candidate_run_id);
    SELECT * INTO published FROM taxonomy_runs WHERE id = candidate_run_id AND status = 'ready_for_review' AND updated_at = expected_updated_at FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy run is no longer ready for review'; END IF;
    IF btrim(operator_name) = '' THEN RAISE EXCEPTION 'operator name is required'; END IF;
    IF NOT EXISTS (SELECT 1 FROM topic_revisions WHERE taxonomy_run_id = candidate_run_id) THEN RAISE EXCEPTION 'taxonomy run has no accepted topics'; END IF;
    INSERT INTO topic_aliases(topic_id, alias, normalized_alias, created_in_run_id) SELECT topic_id, name, normalized_name, candidate_run_id FROM topic_revisions WHERE taxonomy_run_id = candidate_run_id ON CONFLICT DO NOTHING;
    UPDATE taxonomy_runs SET status='published', decision_by=operator_name, decision_at=CURRENT_TIMESTAMP, decision_note=operator_note, published_at=CURRENT_TIMESTAMP WHERE id=candidate_run_id RETURNING * INTO published;
    RETURN published;
END;
$$;
COMMIT;
