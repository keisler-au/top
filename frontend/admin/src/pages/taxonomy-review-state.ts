/** Request ownership remains valid even when a transport ignores abort. */
export class LatestReviewRequest {
  #controller: AbortController | null = null;
  begin(): AbortController {
    this.cancel();
    this.#controller = new AbortController();
    return this.#controller;
  }
  current(controller: AbortController): boolean {
    return this.#controller === controller && !controller.signal.aborted;
  }
  cancel(): void { this.#controller?.abort(); }
}

export function reviewRunId(search: URLSearchParams): number | null {
  const raw = search.get("run");
  const id = raw && /^\d+$/.test(raw) ? Number(raw) : 0;
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}
