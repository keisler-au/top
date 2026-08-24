BEGIN;

CREATE TABLE form_sources (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'google-sheets'
        CONSTRAINT form_sources_source_nonempty CHECK (btrim(source) <> ''),
    form_id TEXT NOT NULL
        CONSTRAINT form_sources_form_id_nonempty CHECK (btrim(form_id) <> ''),
    spreadsheet_id TEXT NOT NULL
        CONSTRAINT form_sources_spreadsheet_id_nonempty
        CHECK (btrim(spreadsheet_id) <> ''),
    sheet_name TEXT NOT NULL DEFAULT 'Form Responses 1'
        CONSTRAINT form_sources_sheet_name_nonempty
        CHECK (btrim(sheet_name) <> ''),
    ignored_headers TEXT[] NOT NULL DEFAULT ARRAY['Timestamp']::text[],
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_read_row INTEGER NOT NULL DEFAULT 1
        CONSTRAINT form_sources_last_read_row_positive
        CHECK (last_read_row >= 1),
    poll_interval_seconds INTEGER NOT NULL DEFAULT 60
        CONSTRAINT form_sources_poll_interval_positive
        CHECK (poll_interval_seconds >= 1),
    next_poll_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_polled_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT form_sources_identity_unique UNIQUE (source, form_id),
    CONSTRAINT form_sources_sheet_unique
        UNIQUE (spreadsheet_id, sheet_name)
);

CREATE INDEX idx_form_sources_due
    ON form_sources (next_poll_at, id)
    WHERE enabled;

ALTER TABLE questions
    ADD COLUMN form_source_id BIGINT
        REFERENCES form_sources (id) ON DELETE RESTRICT;

CREATE INDEX idx_questions_form_source_id
    ON questions (form_source_id)
    WHERE form_source_id IS NOT NULL;

ALTER TABLE original_inputs
    ADD COLUMN source_record_key TEXT
        CONSTRAINT original_inputs_source_record_key_nonempty
        CHECK (
            source_record_key IS NULL
            OR btrim(source_record_key) <> ''
        );

CREATE UNIQUE INDEX idx_original_inputs_source_record
    ON original_inputs (source, source_record_key)
    WHERE source_record_key IS NOT NULL;

COMMIT;
