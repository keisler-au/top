export interface ApiProblem {
  detail?: unknown;
}

function problemMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return null;
  }
  const detail = (body as ApiProblem).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (typeof item !== "object" || item === null) {
        return [];
      }
      const message = "msg" in item ? item.msg : null;
      return typeof message === "string" ? [message] : [];
    });
    return messages.length > 0 ? messages.join("; ") : null;
  }
  return null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, fallback: string) {
    super(problemMessage(body) ?? fallback);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function userFacingError(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = typeof error.body === "object" && error.body !== null && "detail" in error.body
      ? error.body.detail : null;
    const code = typeof detail === "object" && detail !== null && "code" in detail
      ? detail.code : null;
    if (code === "taxonomy_first_run") {
      return "No taxonomy has been published yet. Eligible evidence and a successful automatic candidate are required.";
    }
    if (code === "taxonomy_candidate_processing") {
      return "The first taxonomy candidate is processing. Check its progress in operations.";
    }
    if (code === "taxonomy_automation_blocked") {
      return "Automatic taxonomy creation is blocked. Check the bounded failure code in operations.";
    }
    if (code === "taxonomy_scheduler_unavailable") {
      return "The taxonomy scheduler is unavailable. Check its service and database connection.";
    }
    if (code === "taxonomy_candidate_failed") {
      return "Taxonomy processing failed. An operator must inspect the failed stage and retry it after correcting the cause.";
    }
    if (code === "taxonomy_quality_blocked") {
      return "The taxonomy candidate did not meet the quality gate. An operator must review the rejected evidence or labels before a new candidate can be published.";
    }
    if (error.status >= 500) {
      return "The server could not complete the request. Please try again.";
    }
    return error.message;
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "The request was cancelled.";
  }
  if (error instanceof TypeError) {
    return "The dashboard could not reach the server. Check your connection.";
  }
  return "Something went wrong. Please try again.";
}
