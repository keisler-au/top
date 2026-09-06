export interface EditableArticleSection {
  heading: string;
  paragraphs: string[];
  evidence_ids?: string[];
}

export interface EditableArticleContent {
  standfirst: string;
  sections: EditableArticleSection[];
  [key: string]: unknown;
}

export function editableArticleContent(
  value: Record<string, unknown>,
): EditableArticleContent {
  const sections = Array.isArray(value.sections)
    ? value.sections.flatMap((item): EditableArticleSection[] => {
      if (typeof item !== "object" || item === null) return [];
      const record = item as Record<string, unknown>;
      const paragraphs = Array.isArray(record.paragraphs)
        ? record.paragraphs.filter((paragraph): paragraph is string => (
          typeof paragraph === "string"
        ))
        : [];
      return [{
        heading: typeof record.heading === "string" ? record.heading : "",
        paragraphs,
        ...(Array.isArray(record.evidence_ids)
          ? { evidence_ids: record.evidence_ids.filter(
            (id): id is string => typeof id === "string",
          ) }
          : {}),
      }];
    })
    : [];
  return {
    ...value,
    standfirst: typeof value.standfirst === "string" ? value.standfirst : "",
    sections: sections.length > 0
      ? sections
      : [{ heading: "", paragraphs: [""] }],
  };
}

export function paragraphsFromText(value: string): string[] {
  return value
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

export function parseThemeIds(value: string): number[] {
  const ids = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => Number(item));
  if (ids.some((id) => !Number.isSafeInteger(id) || id < 1)) {
    throw new Error("Theme IDs must be positive whole numbers separated by commas.");
  }
  return [...new Set(ids)];
}

export function parseTopicNames(value: string): string[] {
  return [...new Set(value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean))];
}
