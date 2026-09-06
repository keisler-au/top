import test from "node:test";
import assert from "node:assert/strict";

import { ApiError } from "../dist/assets/api/errors.js";
import {
  restoredTemplateSelection,
  templateDraft,
  templateValidationResult,
} from "../dist/assets/pages/template-admin-state.js";

const template = {
  id: 3,
  name: "Feature",
  description: null,
  status: "active",
  versions: [{
    id: 9,
    version: 2,
    html_source: "<article>{{title}}{{article_body}}</article>",
    allowed_placeholders: ["title", "article_body"],
    used_by_article_count: 4,
    created_by: null,
    created_at: "2026-01-01T00:00:00Z",
  }],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

test("starts create and version editors with recoverable draft values", () => {
  assert.equal(templateDraft().name, "");
  assert.match(templateDraft().htmlSource, /\{\{article_body\}\}/);
  assert.equal(templateDraft(template).htmlSource, "<article>{{title}}{{article_body}}</article>");
});

test("restores the generation selection unless management archived it", () => {
  assert.deepEqual(
    restoredTemplateSelection(
      [template],
      { templateId: 3, versionId: 9 },
      null,
    ),
    { templateId: 3, versionId: 9 },
  );
  assert.equal(
    restoredTemplateSelection(
      [{ ...template, status: "archived" }],
      { templateId: 3, versionId: 9 },
      { templateId: 3, versionId: 9 },
    ),
    null,
  );
});

test("maps unsafe-template responses to the HTML field and error summary", () => {
  const result = templateValidationResult(
    new ApiError(422, { detail: "script elements are not allowed" }, "Invalid template"),
    true,
  );

  assert.equal(result.summary, "script elements are not allowed");
  assert.equal(result.fields.html_source, "script elements are not allowed");
});

test("maps duplicate names and structured validation errors to their fields", () => {
  const duplicate = templateValidationResult(
    new ApiError(409, { detail: "a template with this name already exists" }, "Conflict"),
    true,
  );
  assert.equal(duplicate.fields.name, "a template with this name already exists");

  const validation = templateValidationResult(new ApiError(422, {
    detail: [{ loc: ["body", "created_by"], msg: "String should have at most 200 characters" }],
  }, "Invalid request"), false);
  assert.equal(validation.fields.created_by, "String should have at most 200 characters");
  assert.equal(validation.fields.html_source, undefined);
});
