import type {
  RecommendationStrategy,
  SortDirection,
  TaxonomyQuery,
  TaxonomySort,
  TaxonomyType,
} from "../api/contracts.js";

export interface DashboardState {
  type: TaxonomyType;
  search: string;
  sort: TaxonomySort;
  direction: SortDirection;
  page: number;
  pageSize: number;
}

const taxonomyTypes = new Set<TaxonomyType>(["theme", "topic"]);
const sorts = new Set<TaxonomySort>([
  "name",
  "evidence",
  "articles",
  "approved_articles",
]);
const directions = new Set<SortDirection>(["asc", "desc"]);

function positiveInteger(value: string | null, fallback: number): number {
  if (value === null || !/^\d+$/.test(value)) {
    return fallback;
  }
  const parsed = Number.parseInt(value, 10);
  return parsed > 0 ? parsed : fallback;
}

export function dashboardState(parameters: URLSearchParams): DashboardState {
  const rawType = parameters.get("type") as TaxonomyType | null;
  const rawSort = parameters.get("sort") as TaxonomySort | null;
  const rawDirection = parameters.get("direction") as SortDirection | null;
  const pageSize = Math.min(
    100,
    positiveInteger(parameters.get("page_size"), 25),
  );
  const requestedPage = positiveInteger(parameters.get("page"), 1);
  const page = (requestedPage - 1) * pageSize <= 100_000
    ? requestedPage
    : 1;
  return {
    type: rawType && taxonomyTypes.has(rawType) ? rawType : "theme",
    search: parameters.get("search")?.trim() ?? "",
    sort: rawSort && sorts.has(rawSort) ? rawSort : "evidence",
    direction: rawDirection && directions.has(rawDirection)
      ? rawDirection
      : "desc",
    page,
    pageSize,
  };
}

export function stateAsQuery(state: DashboardState): TaxonomyQuery {
  return {
    type: state.type,
    search: state.search || undefined,
    sort: state.sort,
    direction: state.direction,
    page: state.page,
    pageSize: state.pageSize,
  };
}

export function stateAsSearch(state: DashboardState): string {
  const parameters = new URLSearchParams({
    type: state.type,
    sort: state.sort,
    direction: state.direction,
    page: String(state.page),
    page_size: String(state.pageSize),
  });
  if (state.search) {
    parameters.set("search", state.search);
  }
  return parameters.toString();
}

export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

export function generationUrl(
  type: TaxonomyType,
  key: number | string,
  name: string,
  sourceStrategy?: RecommendationStrategy,
): string {
  const parameters = new URLSearchParams({
    strategy: "specific",
    type,
    key: String(key),
    name,
  });
  if (sourceStrategy) {
    parameters.set("source_strategy", sourceStrategy);
  }
  return `/generate?${parameters}`;
}
