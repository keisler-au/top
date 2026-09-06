import type {
  ArticleQuery,
  ArticleSort,
  ArticleStatus,
  SortDirection,
} from "../api/contracts.js";

export interface ArticlesState {
  status: ArticleStatus | null;
  themeId: number | null;
  topic: string;
  search: string;
  sort: ArticleSort;
  direction: SortDirection;
  page: number;
  pageSize: number;
  failedGenerations: boolean;
}

const statuses = new Set<ArticleStatus>([
  "draft", "ready_for_review", "approved", "archived",
]);
const sorts = new Set<ArticleSort>(["updated", "title", "status"]);

function positiveInteger(value: string | null): number | null {
  if (value === null || !/^\d+$/.test(value)) return null;
  const parsed = Number.parseInt(value, 10);
  return parsed > 0 ? parsed : null;
}

export function articlesState(parameters: URLSearchParams): ArticlesState {
  const rawStatus = parameters.get("status") as ArticleStatus | null;
  const rawSort = parameters.get("sort") as ArticleSort | null;
  const rawDirection = parameters.get("direction");
  const pageSize = Math.min(100, positiveInteger(parameters.get("page_size")) ?? 25);
  const requestedPage = positiveInteger(parameters.get("page")) ?? 1;
  return {
    status: rawStatus && statuses.has(rawStatus) ? rawStatus : null,
    themeId: positiveInteger(parameters.get("theme_id")),
    topic: parameters.get("topic")?.trim() ?? "",
    search: parameters.get("search")?.trim() ?? "",
    sort: rawSort && sorts.has(rawSort) ? rawSort : "updated",
    direction: rawDirection === "asc" ? "asc" : "desc",
    page: (requestedPage - 1) * pageSize <= 100_000 ? requestedPage : 1,
    pageSize,
    failedGenerations: parameters.get("generation_status") === "failed",
  };
}

export function articlesQuery(state: ArticlesState): ArticleQuery {
  return {
    status: state.status ?? undefined,
    themeId: state.themeId ?? undefined,
    topic: state.topic || undefined,
    search: state.search || undefined,
    sort: state.sort,
    direction: state.direction,
    page: state.page,
    pageSize: state.pageSize,
  };
}

export function articlesSearch(state: ArticlesState): string {
  const parameters = new URLSearchParams({
    sort: state.sort,
    direction: state.direction,
    page: String(state.page),
    page_size: String(state.pageSize),
  });
  if (state.status) parameters.set("status", state.status);
  if (state.themeId !== null) parameters.set("theme_id", String(state.themeId));
  if (state.topic) parameters.set("topic", state.topic);
  if (state.search) parameters.set("search", state.search);
  if (state.failedGenerations) parameters.set("generation_status", "failed");
  return parameters.toString();
}

export function articleReturnUrl(parameters: URLSearchParams): string {
  const value = parameters.get("return");
  if (!value) return "/articles";
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin === window.location.origin && url.pathname === "/articles") {
      return `${url.pathname}${url.search}`;
    }
  } catch {
    // Fall through to the safe library route.
  }
  return "/articles";
}
