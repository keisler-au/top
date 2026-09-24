BEGIN;

-- Existing reserved decisions retain their original delta membership on replay.
-- New decisions explicitly choose cumulative membership, independently of the
-- predecessor cutoff kept for audit and new-evidence detection.
ALTER TABLE taxonomy_automation_decisions
    ADD COLUMN membership_mode TEXT NOT NULL DEFAULT 'post_cutoff'
        CHECK (membership_mode IN ('post_cutoff', 'cumulative')),
    ADD COLUMN snapshot_cutoff TIMESTAMPTZ,
    ADD COLUMN failure_attempts INTEGER NOT NULL DEFAULT 0
        CHECK (failure_attempts >= 0),
    ADD COLUMN next_attempt_at TIMESTAMPTZ;

CREATE OR REPLACE FUNCTION protect_taxonomy_automation_decision() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.policy_version IS DISTINCT FROM OLD.policy_version
       OR NEW.evidence_cutoff IS DISTINCT FROM OLD.evidence_cutoff
       OR NEW.predecessor_cutoff IS DISTINCT FROM OLD.predecessor_cutoff
       OR NEW.membership_mode IS DISTINCT FROM OLD.membership_mode
       OR NEW.snapshot_cutoff IS DISTINCT FROM OLD.snapshot_cutoff THEN
        RAISE EXCEPTION 'taxonomy automation decision identity is immutable';
    END IF;
    IF OLD.status = 'manual' AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'terminal taxonomy automation decision is immutable';
    END IF;
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

ALTER TABLE taxonomy_automation_checkpoints
    ADD COLUMN last_scheduler_heartbeat_at TIMESTAMPTZ,
    ADD COLUMN scheduler_heartbeat_expires_at TIMESTAMPTZ,
    ADD COLUMN evaluation_failure_attempts INTEGER NOT NULL DEFAULT 0
        CHECK (evaluation_failure_attempts >= 0),
    ADD COLUMN evaluation_next_attempt_at TIMESTAMPTZ;

COMMIT;
