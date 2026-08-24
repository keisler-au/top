# Google Sheets ingestion

The optional Google Sheets importer polls append-only Google Form response
sheets without exposing the API publicly. Each registered form supplies a
stable `form_id`, a spreadsheet ID and a sheet/tab name. The poller reads the
header row, imports every non-empty cell after `last_read_row`, and advances
the cursor after each complete row.

## Data relationships

```text
form_sources.id
    ↓
questions.form_source_id
    ↓
original_inputs.question_id
    ↓
segment_inputs.original_input_id
```

The registered external `form_id` is stored once in `form_sources`. Questions
reference that registry row; answers reference questions; segments already
reference their original answer. No form columns are duplicated onto segments.

The API includes `question_context.form_id` when an input belongs to a
registered form.

## Google setup

1. Create or select a Google Cloud project and enable the Google Sheets API.
2. Create a service account and download its JSON credential file.
3. Share each response spreadsheet with the service account email as a viewer.
4. Store the credential outside version control, for example:

   ```text
   .secrets/google-sheets.json
   ```

The importer requests only the read-only Sheets scope.

## Register forms

Apply migrations by starting the normal Compose stack, then open the dashboard
Forms page at `/forms`. Enter:

- a permanent form ID;
- the Google Sheets URL or spreadsheet ID;
- the exact response tab name;
- any comma-separated headers that should be ignored;
- the polling interval.

The dashboard registers the source through `POST /form-sources` and displays
its cursor, last/next poll, and last polling error. It can also edit poller
metadata and pause or resume a source. `form_id` is immutable because it is the
stable identifier returned with every imported question and answer.

The equivalent API payload is:

```json
{
  "form_id": "customer-feedback",
  "spreadsheet_id": "1abc123_google_spreadsheet_id",
  "sheet_name": "Form Responses 1",
  "ignored_headers": ["Timestamp", "Email Address"],
  "poll_interval_seconds": 60,
  "enabled": true
}
```

Direct SQL remains useful for recovery or inspection:

```sql
INSERT INTO form_sources (
    form_id,
    spreadsheet_id,
    sheet_name,
    ignored_headers
)
VALUES (
    'customer-feedback',
    '1abc123_google_spreadsheet_id',
    'Form Responses 1',
    ARRAY['Timestamp', 'Email Address']
);
```

Register additional forms through the same screen or endpoint. A
spreadsheet/tab combination can only be registered once.

Inspect the registry and cursors with:

```sql
SELECT
    id,
    form_id,
    spreadsheet_id,
    sheet_name,
    enabled,
    last_read_row,
    last_polled_at,
    last_error
FROM form_sources
ORDER BY id;
```

## Run the importer

The service is behind an optional Compose profile so the normal stack does not
require Google credentials:

```bash
docker compose --profile google-sheets up --build
```

Use a credential at another host path with:

```bash
GOOGLE_SHEETS_CREDENTIALS_FILE=/secure/google-sheets.json \
docker compose --profile google-sheets up --build
```

Useful settings are:

```text
GOOGLE_SHEETS_POLL_INTERVAL=5
GOOGLE_SHEETS_BATCH_SIZE=100
GOOGLE_SHEETS_TIMEOUT_SECONDS=30
```

`poll_interval_seconds` on each `form_sources` row determines how frequently
that particular form becomes due. `GOOGLE_SHEETS_POLL_INTERVAL` controls how
quickly the worker checks the registry when no form is currently due.

## Mapping rules

- The registry's `form_id` becomes both the API `form_id` and `form_key`.
- A case-insensitive hash of the trimmed header becomes `question_key`.
- The header itself becomes the immutable `question_text`.
- Changed header wording creates a new question identity.
- Added columns are discovered automatically.
- Empty answer cells and configured ignored headers are skipped.
- Duplicate non-ignored headers stop that form with an explicit error.
- The sheet row becomes `submission_key`; all answers in a row stay grouped.
- The sheet row and column become `source_record_key`, making retries
  idempotent.

## Append-only requirement

Treat the response tab as an append-only ingestion log. Do not sort it, delete
unread rows, insert rows in the middle, or expect edits to previously imported
rows to be reprocessed. Copy responses into another tab for sorting and manual
analysis.

If a form header changes while the importer is offline, all unread cells in
that column will be interpreted using the header visible when polling resumes.
This is the deliberate tradeoff of the simple sheet-based design.
