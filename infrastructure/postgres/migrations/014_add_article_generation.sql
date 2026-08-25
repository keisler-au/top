BEGIN;

CREATE TABLE article_templates (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL
        CONSTRAINT article_templates_name_nonempty
        CHECK (btrim(name) <> '' AND char_length(name) <= 120),
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CONSTRAINT article_templates_status_valid
        CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_article_templates_name_case_insensitive
    ON article_templates (lower(btrim(name)));

CREATE TABLE article_template_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    template_id BIGINT NOT NULL
        REFERENCES article_templates (id) ON DELETE RESTRICT,
    version INTEGER NOT NULL
        CONSTRAINT article_template_versions_number_positive CHECK (version >= 1),
    html_source TEXT NOT NULL
        CONSTRAINT article_template_versions_html_nonempty CHECK (btrim(html_source) <> ''),
    allowed_placeholders TEXT[] NOT NULL,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT article_template_versions_template_version_unique
        UNIQUE (template_id, version)
);

CREATE OR REPLACE FUNCTION reject_article_template_version_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'article template versions are immutable';
END;
$$;

CREATE TRIGGER article_template_versions_immutable
BEFORE UPDATE OR DELETE ON article_template_versions
FOR EACH ROW
EXECUTE FUNCTION reject_article_template_version_mutation();

ALTER TABLE article_revisions
    ADD COLUMN template_version_id BIGINT
        REFERENCES article_template_versions (id) ON DELETE RESTRICT;

INSERT INTO article_templates (name, description)
VALUES (
    'Standard article',
    'Accessible starter template for evidence-grounded articles.'
);

INSERT INTO article_template_versions (
    template_id,
    version,
    html_source,
    allowed_placeholders
)
SELECT
    id,
    1,
    '<article><header><h1>{{title}}</h1><p>{{standfirst}}</p></header><main>{{article_body}}</main></article>',
    ARRAY['title', 'standfirst', 'article_body']::text[]
FROM article_templates
WHERE name = 'Standard article';

CREATE TABLE article_generation_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending'
        CONSTRAINT article_generation_jobs_status_valid
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dismissed')),
    strategy TEXT NOT NULL
        CONSTRAINT article_generation_jobs_strategy_valid
        CHECK (strategy IN ('specific', 'most-evidence', 'least-covered')),
    taxonomy_type TEXT NOT NULL
        CONSTRAINT article_generation_jobs_taxonomy_type_valid
        CHECK (taxonomy_type IN ('theme', 'topic')),
    taxonomy_key TEXT NOT NULL
        CONSTRAINT article_generation_jobs_taxonomy_key_nonempty
        CHECK (btrim(taxonomy_key) <> ''),
    taxonomy_name TEXT NOT NULL
        CONSTRAINT article_generation_jobs_taxonomy_name_nonempty
        CHECK (btrim(taxonomy_name) <> ''),
    template_version_id BIGINT NOT NULL
        REFERENCES article_template_versions (id) ON DELETE RESTRICT,
    editorial_guidance TEXT
        CONSTRAINT article_generation_jobs_guidance_length
        CHECK (editorial_guidance IS NULL OR char_length(editorial_guidance) <= 4000),
    status_url TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
        CONSTRAINT article_generation_jobs_attempts_nonnegative CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    last_error TEXT,
    resulting_article_id BIGINT
        REFERENCES articles (id) ON DELETE RESTRICT,
    completed_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT article_generation_jobs_lock_consistent CHECK (
        (status = 'processing') = (locked_at IS NOT NULL AND locked_by IS NOT NULL)
    ),
    CONSTRAINT article_generation_jobs_result_consistent CHECK (
        (status = 'completed') = (
            resulting_article_id IS NOT NULL AND completed_at IS NOT NULL
        )
    ),
    CONSTRAINT article_generation_jobs_dismissed_consistent CHECK (
        (status = 'dismissed') = (dismissed_at IS NOT NULL)
    )
);

CREATE INDEX idx_article_generation_jobs_available
    ON article_generation_jobs (available_at, id)
    WHERE status = 'pending';

CREATE INDEX idx_article_generation_jobs_failed
    ON article_generation_jobs (updated_at DESC, id DESC)
    WHERE status = 'failed';

CREATE TABLE article_generation_job_evidence (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL
        REFERENCES article_generation_jobs (id) ON DELETE CASCADE,
    original_input_id BIGINT
        REFERENCES original_inputs (id) ON DELETE RESTRICT,
    segment_input_id BIGINT
        REFERENCES segment_inputs (id) ON DELETE RESTRICT,
    evidence_order INTEGER NOT NULL
        CONSTRAINT article_generation_job_evidence_order_nonnegative
        CHECK (evidence_order >= 0),
    evidence_text TEXT NOT NULL
        CONSTRAINT article_generation_job_evidence_text_nonempty CHECK (btrim(evidence_text) <> ''),
    topic_key TEXT NOT NULL
        CONSTRAINT article_generation_job_evidence_topic_nonempty CHECK (btrim(topic_key) <> ''),
    topic_name TEXT NOT NULL,
    CONSTRAINT article_generation_job_evidence_exactly_one_target
        CHECK (num_nonnulls(original_input_id, segment_input_id) = 1),
    CONSTRAINT article_generation_job_evidence_job_order_unique
        UNIQUE (job_id, evidence_order),
    CONSTRAINT article_generation_job_evidence_job_original_unique
        UNIQUE (job_id, original_input_id),
    CONSTRAINT article_generation_job_evidence_job_segment_unique
        UNIQUE (job_id, segment_input_id)
);

COMMIT;
