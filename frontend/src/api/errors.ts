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
