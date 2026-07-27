\set ON_ERROR_STOP on

DO $$
DECLARE
    required_index TEXT;
BEGIN
    FOREACH required_index IN ARRAY ARRAY[
        'questions_identity_unique',
        'idx_questions_source_form',
        'idx_original_inputs_question_id',
        'idx_original_inputs_submission_key'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE
                schemaname = 'public'
                AND indexname = required_index
        ) THEN
            RAISE EXCEPTION
                'required retrieval index is missing: %',
                required_index;
        END IF;
    END LOOP;
END;
$$;
