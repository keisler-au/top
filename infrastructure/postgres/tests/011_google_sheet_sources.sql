BEGIN;

DO $$
DECLARE
    registered_form_id BIGINT;
    stored_question_id BIGINT;
    resolved_form_id TEXT;
BEGIN
    INSERT INTO form_sources (form_id, spreadsheet_id, sheet_name)
    VALUES ('sql-test-form', 'sql-test-sheet', 'Responses')
    RETURNING id INTO registered_form_id;

    INSERT INTO questions (
        source,
        form_key,
        question_key,
        question_version,
        question_text,
        form_source_id
    )
    VALUES (
        'google-sheets',
        'sql-test-form',
        'header-question',
        1,
        'Question?',
        registered_form_id
    )
    RETURNING id INTO stored_question_id;

    INSERT INTO original_inputs (
        original_text,
        source,
        question_id,
        submission_key,
        source_record_key
    )
    VALUES (
        'Answer',
        'google-sheets',
        stored_question_id,
        'row-2',
        'row-2-column-2'
    );

    SELECT forms.form_id INTO resolved_form_id
    FROM original_inputs AS inputs
    JOIN questions ON questions.id = inputs.question_id
    JOIN form_sources AS forms ON forms.id = questions.form_source_id
    WHERE inputs.source_record_key = 'row-2-column-2';

    IF resolved_form_id IS DISTINCT FROM 'sql-test-form' THEN
        RAISE EXCEPTION 'answer did not resolve to its registered form';
    END IF;
END;
$$;

ROLLBACK;
