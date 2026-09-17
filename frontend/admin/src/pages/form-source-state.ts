import type { FormSourceCreate, FormSourceUpdate } from "../api/contracts.js";

const spreadsheetIdPattern = /^[A-Za-z0-9_-]+$/;
const spreadsheetPathPattern = /\/spreadsheets\/d\/([^/]+)/;

export function spreadsheetId(value: string): string {
  let candidate = value.trim();
  if (!candidate) {
    throw new Error("Enter a spreadsheet ID or Google Sheets URL.");
  }
  if (candidate.includes("://")) {
    let parsed: URL;
    try {
      parsed = new URL(candidate);
    } catch {
      throw new Error("Enter a valid Google Sheets URL.");
    }
    if (
      parsed.protocol !== "https:"
      || parsed.hostname !== "docs.google.com"
    ) {
      throw new Error("The spreadsheet URL must be a Google HTTPS URL.");
    }
    const match = spreadsheetPathPattern.exec(parsed.pathname);
    if (!match?.[1]) {
      throw new Error("The Google Sheets URL does not contain a spreadsheet ID.");
    }
    candidate = match[1];
  }
  if (!spreadsheetIdPattern.test(candidate)) {
    throw new Error("The spreadsheet ID contains unsupported characters.");
  }
  return candidate;
}

export function ignoredHeaders(value: string): string[] {
  const headers: string[] = [];
  const seen = new Set<string>();
  for (const rawHeader of value.split(",")) {
    const header = rawHeader.trim();
    if (!header) continue;
    const key = header.toLocaleLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      headers.push(header);
    }
  }
  return headers;
}

export interface FormSourceFields {
  formId: string;
  spreadsheet: string;
  sheetName: string;
  ignoredHeaders: string;
  pollInterval: string;
  enabled: boolean;
}

function commonFields(fields: FormSourceFields): FormSourceUpdate {
  const sheetName = fields.sheetName.trim();
  if (!sheetName) {
    throw new Error("Enter the sheet or tab name.");
  }
  const interval = Number(fields.pollInterval);
  if (!Number.isInteger(interval) || interval < 1 || interval > 86_400) {
    throw new Error("Polling interval must be between 1 and 86,400 seconds.");
  }
  return {
    spreadsheet_id: spreadsheetId(fields.spreadsheet),
    sheet_name: sheetName,
    ignored_headers: ignoredHeaders(fields.ignoredHeaders),
    poll_interval_seconds: interval,
  };
}

export function createPayload(fields: FormSourceFields): FormSourceCreate {
  const formId = fields.formId.trim();
  if (!formId) {
    throw new Error("Enter a stable form ID.");
  }
  return {
    form_id: formId,
    ...commonFields(fields),
    enabled: fields.enabled,
  } as FormSourceCreate;
}

export function updatePayload(fields: FormSourceFields): FormSourceUpdate {
  return commonFields(fields);
}
