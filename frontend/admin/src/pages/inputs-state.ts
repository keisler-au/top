import type { InputFilters } from "../api/contracts.js";

export interface InputsState { filters: InputFilters; offset: number; }
export const inputTextKeys = ["search", "source", "form_key", "question_key", "submission_key", "topic", "theme", "created_from", "created_to"] as const;
const statuses = new Set(["new", "ineligible", "ready_for_embedding", "ready_for_analysis", "completed"]);
export function inputsState(parameters: URLSearchParams): InputsState {
  const filters: InputFilters = {};
  for (const key of inputTextKeys) {
    const value = parameters.get(key)?.trim();
    if (value) filters[key] = value;
  }
  const status = parameters.get("status");
  if (status && statuses.has(status)) filters.status = status as InputFilters["status"];
  const presence = parameters.get("has_topic");
  if (presence === "true" || presence === "false") filters.has_topic = presence === "true";
  const version = Number(parameters.get("question_version"));
  if (Number.isSafeInteger(version) && version > 0) filters.question_version = version;
  const offset = Number(parameters.get("offset"));
  return { filters, offset: Number.isSafeInteger(offset) && offset >= 0 && offset <= 100000 && offset % 50 === 0 ? offset : 0 };
}
export function inputsSearch(state: InputsState): string {
  const parameters = new URLSearchParams();
  for (const [key, value] of Object.entries(state.filters)) if (value !== undefined) parameters.set(key, String(value));
  if (state.offset) parameters.set("offset", String(state.offset));
  return parameters.toString();
}
export function inputFilterError(filters: InputFilters): string | null {
  if (Boolean(filters.source) !== Boolean(filters.form_key)) return "Enter both Source and Form key to filter a form.";
  if ((filters.question_key || filters.submission_key) && (!filters.source || !filters.form_key)) return "Question and submission filters require Source and Form key.";
  if (filters.question_version && !filters.question_key) return "Question version requires a Question key.";
  if (filters.created_from && filters.created_to && filters.created_from > filters.created_to) return "Received from must be on or before Received through.";
  return null;
}
