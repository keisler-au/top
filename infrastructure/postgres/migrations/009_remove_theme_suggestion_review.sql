BEGIN;

ALTER TABLE theme_suggestions
    DROP CONSTRAINT theme_suggestions_reviewed_at_consistent,
    DROP COLUMN review_status,
    DROP COLUMN reviewed_at;

COMMIT;
