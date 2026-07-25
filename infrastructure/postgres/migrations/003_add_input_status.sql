BEGIN;

ALTER TABLE original_inputs
    ADD COLUMN status TEXT NOT NULL DEFAULT 'new'
        CONSTRAINT original_inputs_status_valid
        CHECK (status IN ('new', 'ineligible', 'ready_for_embedding'));

UPDATE original_inputs
SET status = 'ready_for_embedding'
WHERE eligible = TRUE;

ALTER TABLE original_inputs
    DROP COLUMN eligible;

CREATE INDEX idx_original_inputs_new
    ON original_inputs (id)
    WHERE status = 'new';

COMMIT;
