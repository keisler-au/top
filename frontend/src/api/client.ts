import type {
  DashboardSummary,
  EvidenceItem,
  FormSource,
  FormSourceCreate,
  FormSourceUpdate,
  PageResponse,
  RecommendationResponse,
  RecommendationStrategy,
  TaxonomyItem,
  TaxonomyQuery,
  TaxonomyType,
} from "./contracts.js";
import { ApiError } from "./errors.js";

export interface RequestOptions {
  signal?: AbortSignal;
}

export type FetchImplementation = typeof fetch;

function appendIfPresent(
  parameters: URLSearchParams,
  name: string,
  value: string | number | undefined,
): void {
  if (value !== undefined && value !== "") {
    parameters.set(name, String(value));
  }
}

export class ApiClient {
  readonly #baseUrl: string;
  readonly #fetch: FetchImplementation;

  constructor(baseUrl = "", fetchImplementation?: FetchImplementation) {
    this.#baseUrl = baseUrl.replace(/\/$/, "");
    this.#fetch = fetchImplementation ?? globalThis.fetch.bind(globalThis);
  }

  async #request<T>(
    method: "GET" | "POST" | "PATCH",
    path: string,
    body?: unknown,
    options: RequestOptions = {},
  ): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    const response = await this.#fetch(`${this.#baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: options.signal,
    });

    const contentType = response.headers.get("content-type") ?? "";
    const responseBody: unknown = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      throw new ApiError(
        response.status,
        responseBody,
        `Request failed with status ${response.status}.`,
      );
    }
    return responseBody as T;
  }

  #get<T>(path: string, options: RequestOptions = {}): Promise<T> {
    return this.#request("GET", path, undefined, options);
  }

  #post<T>(
    path: string,
    body?: unknown,
    options: RequestOptions = {},
  ): Promise<T> {
    return this.#request("POST", path, body, options);
  }

  #patch<T>(
    path: string,
    body: unknown,
    options: RequestOptions = {},
  ): Promise<T> {
    return this.#request("PATCH", path, body, options);
  }

  summary(options?: RequestOptions): Promise<DashboardSummary> {
    return this.#get("/dashboard/summary", options);
  }

  taxonomy(
    query: TaxonomyQuery,
    options?: RequestOptions,
  ): Promise<PageResponse<TaxonomyItem>> {
    const parameters = new URLSearchParams({ type: query.type });
    appendIfPresent(parameters, "search", query.search?.trim());
    appendIfPresent(parameters, "sort", query.sort);
    appendIfPresent(parameters, "direction", query.direction);
    appendIfPresent(parameters, "page", query.page);
    appendIfPresent(parameters, "page_size", query.pageSize);
    return this.#get(`/taxonomy?${parameters}`, options);
  }

  taxonomyDetail(
    type: TaxonomyType,
    key: number | string,
    options?: RequestOptions,
  ): Promise<TaxonomyItem> {
    return this.#get(
      `/taxonomy/${type}/${encodeURIComponent(String(key))}`,
      options,
    );
  }

  evidence(
    type: TaxonomyType,
    key: number | string,
    page = 1,
    pageSize = 25,
    options?: RequestOptions,
  ): Promise<PageResponse<EvidenceItem>> {
    const parameters = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    return this.#get(
      `/taxonomy/${type}/${encodeURIComponent(String(key))}/evidence?${parameters}`,
      options,
    );
  }

  recommendations(
    type: TaxonomyType,
    strategy: RecommendationStrategy,
    limit = 5,
    options?: RequestOptions,
  ): Promise<RecommendationResponse> {
    const parameters = new URLSearchParams({
      type,
      strategy,
      limit: String(limit),
    });
    return this.#get(`/recommendations/articles?${parameters}`, options);
  }

  formSources(
    page = 1,
    pageSize = 100,
    options?: RequestOptions,
  ): Promise<PageResponse<FormSource>> {
    const parameters = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    return this.#get(`/form-sources?${parameters}`, options);
  }

  createFormSource(
    payload: FormSourceCreate,
    options?: RequestOptions,
  ): Promise<FormSource> {
    return this.#post("/form-sources", payload, options);
  }

  updateFormSource(
    id: number,
    payload: FormSourceUpdate,
    options?: RequestOptions,
  ): Promise<FormSource> {
    return this.#patch(`/form-sources/${id}`, payload, options);
  }

  setFormSourceEnabled(
    id: number,
    enabled: boolean,
    options?: RequestOptions,
  ): Promise<FormSource> {
    const action = enabled ? "enable" : "disable";
    return this.#post(`/form-sources/${id}/${action}`, undefined, options);
  }
}

export function apiBaseUrl(documentRoot: Document = document): string {
  const configured = documentRoot
    .querySelector<HTMLMetaElement>('meta[name="api-base-url"]')
    ?.content.trim();
  return configured || "";
}
