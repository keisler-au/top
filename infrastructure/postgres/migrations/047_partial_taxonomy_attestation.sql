BEGIN;

-- Labels may repeat across questions; reconciliation owns their equivalence.
ALTER TABLE taxonomy_provisional_topics DROP CONSTRAINT taxonomy_provisional_topics_taxonomy_run_id_normalized_name_key;
CREATE FUNCTION guard_provisional_question_name() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
 PERFORM id FROM taxonomy_runs WHERE id=NEW.taxonomy_run_id FOR UPDATE;
 IF EXISTS (SELECT 1 FROM taxonomy_provisional_topics p
    JOIN taxonomy_cluster_candidates old_cluster ON old_cluster.taxonomy_run_id=p.taxonomy_run_id AND old_cluster.id=p.cluster_candidate_id
    JOIN taxonomy_cluster_candidates new_cluster ON new_cluster.taxonomy_run_id=NEW.taxonomy_run_id AND new_cluster.id=NEW.cluster_candidate_id
    WHERE p.taxonomy_run_id=NEW.taxonomy_run_id AND p.normalized_name=NEW.normalized_name
      AND old_cluster.question_id=new_cluster.question_id) THEN
    RAISE EXCEPTION 'duplicate provisional topic name within question';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER provisional_question_name BEFORE INSERT ON taxonomy_provisional_topics
FOR EACH ROW EXECUTE FUNCTION guard_provisional_question_name();

-- One computed owner for release consistency and coverage. Both the quality
-- worker and publication transitions use these facts, never caller signals.
CREATE FUNCTION taxonomy_publication_facts(run_id BIGINT) RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE facts JSONB; failures TEXT[] := ARRAY[]::TEXT[]; partial_policy BOOLEAN;
BEGIN
    SELECT configuration->>'cluster_policy_version' = 'partial-topic-policy/v1'
      INTO partial_policy FROM taxonomy_runs WHERE id=run_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy run not found'; END IF;
    SELECT jsonb_build_object(
        'evidence_count', count(*),
        'evidence_with_topic_count', count(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM topic_memberships m WHERE m.taxonomy_run_id=run_id AND m.evidence_id=e.id)),
        'evidence_without_topic_count', count(*) FILTER (WHERE NOT EXISTS (
            SELECT 1 FROM topic_memberships m WHERE m.taxonomy_run_id=run_id AND m.evidence_id=e.id)),
        'question_count', count(DISTINCT i.question_id),
        'submission_count', count(DISTINCT (i.source,q.form_key,i.submission_key)) FILTER (WHERE i.submission_key IS NOT NULL)
    ) INTO facts FROM taxonomy_run_evidence e JOIN original_inputs i ON i.id=e.original_input_id
      JOIN questions q ON q.id=i.question_id WHERE e.taxonomy_run_id=run_id;
    facts := facts || jsonb_build_object(
        'canonical_topic_count', (SELECT count(*) FROM topic_revisions WHERE taxonomy_run_id=run_id),
        'clustered_count', (SELECT count(*) FROM taxonomy_cluster_memberships WHERE taxonomy_run_id=run_id AND decision='clustered'),
        'noise_count', (SELECT count(*) FROM taxonomy_cluster_memberships WHERE taxonomy_run_id=run_id AND decision='noise'),
        'naming_attempt_count', (SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE taxonomy_run_id=run_id),
        'accepted_topic_count', (SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE taxonomy_run_id=run_id AND accepted),
        'rejected_topic_count', (SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE taxonomy_run_id=run_id AND NOT accepted),
        'duplicate_topic_count', (SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE taxonomy_run_id=run_id AND validation_errors @> ARRAY['duplicate_topic']),
        'candidate_theme_count', (SELECT count(*) FROM taxonomy_candidate_themes WHERE taxonomy_run_id=run_id),
        'reconciled_theme_count', (SELECT count(*) FROM taxonomy_reconciled_themes WHERE taxonomy_run_id=run_id)
    );
    IF (facts->>'canonical_topic_count')::bigint < 1 THEN failures := array_append(failures,'canonical_topics_missing'); END IF;
    IF (facts->>'evidence_count')::bigint <> (facts->>'clustered_count')::bigint + (facts->>'noise_count')::bigint THEN
        failures := array_append(failures,'snapshot_incomplete');
    END IF;
    IF EXISTS (SELECT 1 FROM topic_revisions r WHERE r.taxonomy_run_id=run_id AND
         (r.support_count = 0 OR r.support_count <> (SELECT count(*) FROM topic_memberships m
          WHERE m.taxonomy_run_id=run_id AND m.topic_revision_id=r.id))) THEN
        failures := array_append(failures,'topic_membership_inconsistent');
    END IF;
    IF partial_policy THEN
        IF EXISTS (SELECT 1 FROM unnest(ARRAY['snapshot','clustering','topic_naming','topic_reconciliation','theme_inference','theme_reconciliation']) required(stage)
            WHERE NOT EXISTS (SELECT 1 FROM taxonomy_run_stages s WHERE s.taxonomy_run_id=run_id
                AND s.stage=required.stage AND s.status='completed')) THEN
            failures := array_append(failures,'processing_unfinished');
        END IF;
        IF EXISTS (SELECT 1 FROM topic_revisions r WHERE r.taxonomy_run_id=run_id AND NOT EXISTS
            (SELECT 1 FROM taxonomy_canonical_topic_antecedents a WHERE a.taxonomy_run_id=run_id AND a.topic_revision_id=r.id))
           OR EXISTS (SELECT 1 FROM taxonomy_provisional_topics p WHERE p.taxonomy_run_id=run_id AND NOT EXISTS
            (SELECT 1 FROM taxonomy_canonical_topic_antecedents a WHERE a.taxonomy_run_id=run_id AND a.provisional_topic_id=p.id))
           OR EXISTS (SELECT 1 FROM taxonomy_canonical_topic_antecedents a JOIN taxonomy_topic_reconciliation_decisions d
                ON d.taxonomy_run_id=a.taxonomy_run_id AND d.id=a.reconciliation_decision_id
                WHERE a.taxonomy_run_id=run_id AND (NOT d.accepted OR NOT a.provisional_topic_id=ANY(d.provisional_topic_ids))) THEN
            failures := array_append(failures,'topic_trace_missing');
        END IF;
        IF EXISTS (
            (SELECT a.topic_revision_id,m.evidence_id FROM taxonomy_canonical_topic_antecedents a
                JOIN taxonomy_provisional_topics p ON p.taxonomy_run_id=a.taxonomy_run_id AND p.id=a.provisional_topic_id
                JOIN taxonomy_cluster_memberships m ON m.taxonomy_run_id=p.taxonomy_run_id AND m.cluster_candidate_id=p.cluster_candidate_id AND m.decision='clustered'
                WHERE a.taxonomy_run_id=run_id
             EXCEPT SELECT topic_revision_id,evidence_id FROM topic_memberships WHERE taxonomy_run_id=run_id)
            UNION ALL
            (SELECT topic_revision_id,evidence_id FROM topic_memberships WHERE taxonomy_run_id=run_id
             EXCEPT SELECT a.topic_revision_id,m.evidence_id FROM taxonomy_canonical_topic_antecedents a
                JOIN taxonomy_provisional_topics p ON p.taxonomy_run_id=a.taxonomy_run_id AND p.id=a.provisional_topic_id
                JOIN taxonomy_cluster_memberships m ON m.taxonomy_run_id=p.taxonomy_run_id AND m.cluster_candidate_id=p.cluster_candidate_id AND m.decision='clustered'
                WHERE a.taxonomy_run_id=run_id)
        ) THEN failures := array_append(failures,'antecedent_membership_inconsistent'); END IF;
        -- Match the complete frozen attempt, never just a repeated label.
        IF EXISTS (SELECT 1 FROM taxonomy_topic_naming_attempts a WHERE a.taxonomy_run_id=run_id
            AND NOT EXISTS (
                SELECT 1 FROM taxonomy_model_requests req JOIN taxonomy_model_responses res
                  ON res.taxonomy_run_id=req.taxonomy_run_id AND res.taxonomy_model_request_id=req.id
                WHERE req.taxonomy_run_id=run_id AND req.stage='topic_naming'
                  AND req.request_context=a.request_context AND req.model=a.model
                  AND req.prompt_version=a.prompt_version AND req.prompt_sha256=a.prompt_sha256
                  AND res.raw_response=a.raw_response
                  AND res.accepted=a.accepted AND res.validation_errors=a.validation_errors))
           OR EXISTS (SELECT 1 FROM taxonomy_provisional_topics p JOIN taxonomy_topic_naming_attempts a
                ON a.taxonomy_run_id=p.taxonomy_run_id AND a.id=p.naming_attempt_id
                WHERE p.taxonomy_run_id=run_id AND (
                    p.name IS DISTINCT FROM btrim(regexp_replace(a.raw_response->>'name', '\s+', ' ', 'g'))
                    OR p.description IS DISTINCT FROM regexp_replace(a.raw_response->>'description', '^\s+|\s+$', '', 'g')))
           OR EXISTS (SELECT 1 FROM taxonomy_topic_reconciliation_decisions d WHERE d.taxonomy_run_id=run_id
                AND d.decision_kind='model' AND NOT EXISTS (
                    SELECT 1 FROM taxonomy_model_requests req JOIN taxonomy_model_responses res
                      ON res.taxonomy_run_id=req.taxonomy_run_id AND res.taxonomy_model_request_id=req.id
                    WHERE req.taxonomy_run_id=run_id AND req.id=d.taxonomy_model_request_id
                      AND req.stage='topic_reconciliation' AND res.accepted=d.accepted
                      AND res.raw_response=d.decision AND res.validation_errors=d.validation_errors))
           OR EXISTS (SELECT 1 FROM taxonomy_theme_inference_attempts a WHERE a.taxonomy_run_id=run_id
                AND NOT EXISTS (
                    SELECT 1 FROM taxonomy_model_requests req JOIN taxonomy_model_responses res
                      ON res.taxonomy_run_id=req.taxonomy_run_id AND res.taxonomy_model_request_id=req.id
                    WHERE req.taxonomy_run_id=run_id AND req.stage='theme_inference'
                      AND req.request_context=a.request_context AND req.model=a.model
                  AND req.prompt_version=a.prompt_version AND req.prompt_sha256=a.prompt_sha256
                  AND res.raw_response=a.raw_response
                      AND res.accepted=a.accepted AND res.validation_errors=a.validation_errors)) THEN
            failures := array_append(failures,'model_trace_missing');
        END IF;
        IF EXISTS (SELECT 1 FROM taxonomy_cluster_candidates c WHERE c.taxonomy_run_id=run_id
            AND c.eligible AND NOT EXISTS (SELECT 1 FROM taxonomy_topic_naming_attempts a
                WHERE a.taxonomy_run_id=run_id AND a.cluster_candidate_id=c.id))
           OR EXISTS (SELECT 1 FROM taxonomy_topic_naming_attempts a WHERE a.taxonomy_run_id=run_id
                AND a.accepted AND NOT EXISTS (SELECT 1 FROM taxonomy_provisional_topics p
                    WHERE p.taxonomy_run_id=run_id AND p.naming_attempt_id=a.id)) THEN
            failures := array_append(failures,'topic_trace_missing');
        END IF;
        IF EXISTS (SELECT 1 FROM taxonomy_candidate_themes t WHERE t.taxonomy_run_id=run_id
            AND NOT EXISTS (SELECT 1 FROM taxonomy_theme_inference_attempts a
                WHERE a.taxonomy_run_id=run_id AND a.accepted AND a.raw_response->>'create_theme'='true'
                  AND a.request_context=t.inference_request AND a.raw_response=t.inference_response
                  AND regexp_replace(a.raw_response->>'name', '^\s+|\s+$', '', 'g')=t.name
                  AND regexp_replace(a.raw_response->>'description', '^\s+|\s+$', '', 'g')=t.description
                  AND regexp_replace(a.raw_response->>'rationale', '^\s+|\s+$', '', 'g')=t.rationale))
           OR EXISTS (SELECT 1 FROM taxonomy_candidate_themes t WHERE t.taxonomy_run_id=run_id
                AND NOT EXISTS (SELECT 1 FROM taxonomy_reconciled_theme_antecedents a
                    WHERE a.taxonomy_run_id=run_id AND a.candidate_theme_id=t.id)) THEN
            failures := array_append(failures,'theme_trace_missing');
        END IF;

    END IF;
    IF EXISTS (SELECT 1 FROM taxonomy_reconciled_themes t WHERE t.taxonomy_run_id=run_id AND NOT EXISTS (
         SELECT 1 FROM taxonomy_reconciled_theme_antecedents a JOIN taxonomy_candidate_theme_topics l
           ON l.taxonomy_run_id=a.taxonomy_run_id AND l.candidate_theme_id=a.candidate_theme_id
         WHERE a.taxonomy_run_id=run_id AND a.reconciled_theme_id=t.id)) THEN
        failures := array_append(failures,'theme_membership_inconsistent');
    END IF;
    IF partial_policy AND EXISTS (SELECT 1 FROM taxonomy_candidate_themes t WHERE t.taxonomy_run_id=run_id
        AND ((SELECT count(*) FROM taxonomy_candidate_theme_topics l
              WHERE l.taxonomy_run_id=run_id AND l.candidate_theme_id=t.id) < 2
          OR (SELECT array_agg(l.topic_revision_id ORDER BY l.topic_revision_id)
              FROM taxonomy_candidate_theme_topics l WHERE l.taxonomy_run_id=run_id AND l.candidate_theme_id=t.id)
             IS DISTINCT FROM (SELECT array_agg(value::bigint ORDER BY value::bigint)
                FROM jsonb_array_elements_text(t.inference_response->'topic_revision_ids') value))) THEN
        failures := array_append(failures,'theme_membership_inconsistent');
    END IF;
    RETURN facts || jsonb_build_object('integrity_failures',to_jsonb(failures));
END;
$$;

-- Optional theme projection; publication transitions remain PTR-5.
CREATE OR REPLACE FUNCTION materialize_taxonomy_theme_revisions(candidate_run_id BIGINT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE candidate taxonomy_runs; prior_run_id BIGINT; reconciled RECORD;
        candidate_topics BIGINT[]; matched_ids BIGINT[]; assigned_theme_id BIGINT;
        prior RECORD; current RECORD; predecessor_count INTEGER; successor_count INTEGER;
BEGIN
    SELECT * INTO candidate FROM taxonomy_runs WHERE id=candidate_run_id FOR UPDATE;
    IF NOT FOUND OR candidate.status NOT IN ('ready_for_review','published') THEN RAISE EXCEPTION 'taxonomy run is not ready for theme materialization'; END IF;
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


COMMIT;
