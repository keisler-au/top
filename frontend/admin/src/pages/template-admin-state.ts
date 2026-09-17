import type { ArticleTemplate } from "../api/contracts.js";
import { ApiError, userFacingError } from "../api/errors.js";

export type TemplateField = "name" | "description" | "html_source" | "created_by";

export interface TemplateDraft {
  name: string;
  description: string;
  htmlSource: string;
  createdBy: string;
}

export interface TemplateValidationResult {
  summary: string;
  fields: Partial<Record<TemplateField, string>>;
}

export interface TemplateSelection {
  templateId: number;
  versionId: number;
}

const defaultSource = "<article><header><h1>{{title}}</h1><p>{{standfirst}}</p></header><main>{{article_body}}</main></article>";

function isTemplateField(value: unknown): value is TemplateField {
  return value === "name" || value === "description"
    || value === "html_source" || value === "created_by";
}

export function templateDraft(template?: ArticleTemplate): TemplateDraft {
  return {
    name: "",
    description: "",
    htmlSource: template?.versions[0]?.html_source ?? defaultSource,
    createdBy: "",
  };
}

function validSelection(
  templates: ArticleTemplate[],
  selection: TemplateSelection | null,
): TemplateSelection | null {
  if (!selection) return null;
  const template = templates.find(
    (item) => item.id === selection.templateId && item.status === "active",
  );
  return template?.versions.some((version) => version.id === selection.versionId)
    ? selection
    : null;
}

export function restoredTemplateSelection(
  templates: ArticleTemplate[],
  original: TemplateSelection | null,
  current: TemplateSelection | null,
): TemplateSelection | null {
  const restored = validSelection(templates, original) ?? validSelection(templates, current);
  if (restored) return restored;
  const fallback = templates.find(
    (template) => template.status === "active" && template.versions.length > 0,
  );
  return fallback?.versions[0]
    ? { templateId: fallback.id, versionId: fallback.versions[0].id }
    : null;
}

function apiValidationFields(error: ApiError): Partial<Record<TemplateField, string>> {
  const fields: Partial<Record<TemplateField, string>> = {};
  if (typeof error.body === "object" && error.body !== null && "detail" in error.body) {
    const detail = (error.body as { detail?: unknown }).detail;
    if (Array.isArray(detail)) {
      for (const item of detail) {
        if (typeof item !== "object" || item === null) continue;
        const location = "loc" in item && Array.isArray(item.loc) ? item.loc : [];
        const field = location.at(-1);
        const message = "msg" in item && typeof item.msg === "string" ? item.msg : null;
        if (message && isTemplateField(field)) {
          fields[field] = message;
        }
      }
    }
  }
  return fields;
}

export function templateValidationResult(
  error: unknown,
  creatingTemplate: boolean,
): TemplateValidationResult {
  const summary = userFacingError(error);
  if (!(error instanceof ApiError)) return { summary, fields: {} };
  const fields = apiValidationFields(error);
  if (Object.keys(fields).length === 0) {
    if (creatingTemplate && error.status === 409) fields.name = summary;
    else if (error.status === 422) fields.html_source = summary;
  }
  return { summary, fields };
}
