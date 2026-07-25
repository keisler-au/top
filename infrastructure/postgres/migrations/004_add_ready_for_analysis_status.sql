BEGIN;

ALTER TABLE original_inputs
    DROP CONSTRAINT original_inputs_status_valid,
    ADD CONSTRAINT original_inputs_status_valid
        CHECK (
            status IN (
                'new',
                'ineligible',
                'ready_for_embedding',
                'ready_for_analysis'
            )
        );

CREATE INDEX idx_original_inputs_ready_for_embedding
    ON original_inputs (id)
    WHERE status = 'ready_for_embedding';

COMMIT;
