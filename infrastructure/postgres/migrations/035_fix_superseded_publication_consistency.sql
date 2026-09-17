BEGIN;

-- A superseded run is still a historical publication.  Rollback migration 033
-- introduced that state but left the original published-at check too narrow.
ALTER TABLE taxonomy_runs DROP CONSTRAINT taxonomy_runs_publication_consistent;
ALTER TABLE taxonomy_runs ADD CONSTRAINT taxonomy_runs_publication_consistent
    CHECK ((status IN ('published', 'superseded')) = (published_at IS NOT NULL));

COMMIT;
