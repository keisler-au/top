\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    first_question_id BIGINT;
    second_question_id BIGINT;
    input_id BIGINT;
    segment_id BIGINT;
    suggestion_id BIGINT;
    mutation_rejected BOOLEAN := FALSE;
    duplicate_rejected BOOLEAN := FALSE;
    deletion_rejected BOOLEAN := FALSE;
BEGIN
    INSERT INTO questions (
        source,
        form_key,
        question_key,
        question_version,
        question_text
    )
    VALUES (
        'wp1-test',
        'survey',
        'barrier',
        1,
        'What prevents you from purchasing?'
    )
    RETURNING id INTO first_question_id;

    BEGIN
        INSERT INTO questions (
            source,
            form_key,
            question_key,
            question_version,
            question_text
        )
        VALUES (
            'wp1-test',
            'survey',
            'barrier',
            1,
            'A conflicting snapshot'
        );
    EXCEPTION
        WHEN unique_violation THEN
            duplicate_rejected := TRUE;
    END;
    IF NOT duplicate_rejected THEN
        RAISE EXCEPTION 'duplicate question identity was accepted';
    END IF;

    BEGIN
        UPDATE questions
        SET question_text = 'Mutated question text'
        WHERE id = first_question_id;
    EXCEPTION
        WHEN raise_exception THEN
            mutation_rejected := TRUE;
    END;
    IF NOT mutation_rejected THEN
        RAISE EXCEPTION 'question mutation was accepted';
    END IF;

    INSERT INTO questions (
        source,
        form_key,
        question_key,
        question_version,
        question_text
    )
    VALUES (
        'wp1-test',
        'survey',
        'alternative',
        1,
        'What else prevents you from purchasing?'
    )
    RETURNING id INTO second_question_id;

    INSERT INTO original_inputs (
        original_text,
        source,
        question_id,
        submission_key
    )
    VALUES (
        'Price',
        'wp1-test',
        first_question_id,
        'submission-1'
    )
    RETURNING id INTO input_id;

    mutation_rejected := FALSE;
    BEGIN
        UPDATE original_inputs
        SET question_id = second_question_id
        WHERE id = input_id;
    EXCEPTION
        WHEN raise_exception THEN
            mutation_rejected := TRUE;
    END;
    IF NOT mutation_rejected THEN
        RAISE EXCEPTION 'original_inputs.question_id mutation was accepted';
    END IF;

    BEGIN
        DELETE FROM questions WHERE id = first_question_id;
    EXCEPTION
        WHEN foreign_key_violation THEN
            deletion_rejected := TRUE;
    END;
    IF NOT deletion_rejected THEN
        RAISE EXCEPTION 'referenced question deletion was accepted';
    END IF;

    INSERT INTO input_embeddings (
        original_input_id,
        embedding,
        embedding_model
    )
    VALUES (input_id, '[0.1,0.2]', 'wp1-test');

    duplicate_rejected := FALSE;
    BEGIN
        INSERT INTO input_embeddings (
            original_input_id,
            embedding,
            embedding_model
        )
        VALUES (input_id, '[0.2,0.3]', 'wp1-test');
    EXCEPTION
        WHEN unique_violation THEN
            duplicate_rejected := TRUE;
    END;
    IF NOT duplicate_rejected THEN
        RAISE EXCEPTION 'second original-input embedding was accepted';
    END IF;

    INSERT INTO segment_inputs (
        original_input_id,
        segment_order,
        segment_text
    )
    VALUES (input_id, 0, 'Price')
    RETURNING id INTO segment_id;

    INSERT INTO input_embeddings (
        segment_input_id,
        embedding,
        embedding_model
    )
    VALUES (segment_id, '[0.1,0.2]', 'wp1-test');

    duplicate_rejected := FALSE;
    BEGIN
        INSERT INTO input_embeddings (
            segment_input_id,
            embedding,
            embedding_model
        )
        VALUES (segment_id, '[0.2,0.3]', 'wp1-test');
    EXCEPTION
        WHEN unique_violation THEN
            duplicate_rejected := TRUE;
    END;
    IF NOT duplicate_rejected THEN
        RAISE EXCEPTION 'second segment-input embedding was accepted';
    END IF;

    INSERT INTO original_inputs (original_text, source)
    VALUES ('Generic input', 'wp1-generic')
    RETURNING id INTO input_id;

    IF EXISTS (
        SELECT 1
        FROM original_inputs
        WHERE
            id = input_id
            AND (question_id IS NOT NULL OR submission_key IS NOT NULL)
    ) THEN
        RAISE EXCEPTION 'generic input acquired question context';
    END IF;

    INSERT INTO theme_suggestions (
        action,
        proposed_name,
        proposed_description,
        rationale,
        group_fingerprint
    )
    VALUES (
        'new',
        'WP1 test',
        'WP1 test description',
        'WP1 test rationale',
        repeat('a', 64)
    )
    RETURNING id INTO suggestion_id;

    IF NOT EXISTS (
        SELECT 1
        FROM theme_suggestions
        WHERE
            id = suggestion_id
            AND materialized_theme_id IS NULL
            AND materialized_at IS NULL
    ) THEN
        RAISE EXCEPTION 'new suggestion did not default to pending';
    END IF;

    IF to_regclass('idx_theme_suggestions_unmaterialized') IS NULL THEN
        RAISE EXCEPTION 'unmaterialized suggestion index is missing';
    END IF;
END;
$$;

ROLLBACK;
