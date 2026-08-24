import test from "node:test";
import assert from "node:assert/strict";

import {
  createPayload,
  ignoredHeaders,
  spreadsheetId,
  updatePayload,
} from "../dist/assets/pages/form-source-state.js";

const fields = {
  formId: " customer-feedback ",
  spreadsheet: "https://docs.google.com/spreadsheets/d/sheet_123-abc/edit#gid=0",
  sheetName: " Form Responses 1 ",
  ignoredHeaders: " Timestamp, Email, timestamp,  ",
  pollInterval: "60",
  enabled: true,
};

test("normalizes spreadsheet IDs and Google Sheets URLs", () => {
  assert.equal(spreadsheetId(" sheet_123 "), "sheet_123");
  assert.equal(spreadsheetId(fields.spreadsheet), "sheet_123-abc");
  assert.throws(
    () => spreadsheetId("http://example.com/sheet"),
    /Google HTTPS URL/,
  );
});

test("normalizes and deduplicates ignored headers", () => {
  assert.deepEqual(
    ignoredHeaders(" Timestamp, Email, timestamp, , Email "),
    ["Timestamp", "Email"],
  );
});

test("builds create and update payloads", () => {
  assert.deepEqual(createPayload(fields), {
    form_id: "customer-feedback",
    spreadsheet_id: "sheet_123-abc",
    sheet_name: "Form Responses 1",
    ignored_headers: ["Timestamp", "Email"],
    poll_interval_seconds: 60,
    enabled: true,
  });
  assert.deepEqual(updatePayload(fields), {
    spreadsheet_id: "sheet_123-abc",
    sheet_name: "Form Responses 1",
    ignored_headers: ["Timestamp", "Email"],
    poll_interval_seconds: 60,
  });
});

test("rejects invalid registration fields", () => {
  assert.throws(
    () => createPayload({ ...fields, formId: " " }),
    /stable form ID/,
  );
  assert.throws(
    () => createPayload({ ...fields, pollInterval: "0" }),
    /between 1 and 86,400/,
  );
  assert.throws(
    () => createPayload({ ...fields, sheetName: " " }),
    /sheet or tab name/,
  );
});
