export type TaxonomyType = "theme" | "topic";
export type CoverageState = "no_evidence" | "uncovered" | "covered";
export type EvidenceType = "original" | "segment";
export type RecommendationStrategy = "most-evidence" | "least-covered";
export type TaxonomySort =
  | "name"
  | "evidence"
  | "articles"
  | "approved_articles";
export type SortDirection = "asc" | "desc";

export interface DashboardSummary {
  evidence_count: number;
  theme_count: number;
  topic_count: number;
  article_count: number;
  awaiting_approval_count: number;
  failed_generation_count: number;
}

export interface TaxonomyItem {
  type: TaxonomyType;
  key: number | string;
  name: string;
  description: string | null;
  evidence_count: number;
  article_count: number;
  approved_article_count: number;
  coverage_state: CoverageState;
  generation_eligible: boolean;
}

export interface PageResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface EvidenceQuestionContext {
  form_key: string;
  form_id: string | null;
  question_key: string;
  question_version: number;
  question_text: string;
}

export interface EvidenceItem {
  id: string;
  type: EvidenceType;
  excerpt: string;
  original_text: string;
  original_input_id: number;
  segment_order: number | null;
  topic_key: string;
  topic_name: string;
  source: string;
  submission_key: string | null;
  source_record_key: string | null;
  question_context: EvidenceQuestionContext | null;
  created_at: string;
}

export interface RecommendationItem extends TaxonomyItem {
  explanation: string;
}

export interface RecommendationResponse {
  taxonomy_type: TaxonomyType;
  strategy: RecommendationStrategy;
  items: RecommendationItem[];
}

export interface TaxonomyQuery {
  type: TaxonomyType;
  search?: string;
  sort?: TaxonomySort;
  direction?: SortDirection;
  page?: number;
  pageSize?: number;
}

export interface FormSource {
  id: number;
  source: string;
  form_id: string;
  spreadsheet_id: string;
  sheet_name: string;
  ignored_headers: string[];
  enabled: boolean;
  last_read_row: number;
  poll_interval_seconds: number;
  next_poll_at: string;
  last_polled_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface FormSourceCreate {
  form_id: string;
  spreadsheet_id: string;
  sheet_name: string;
  ignored_headers: string[];
  poll_interval_seconds: number;
  enabled: boolean;
}

export interface FormSourceUpdate {
  spreadsheet_id?: string;
  sheet_name?: string;
  ignored_headers?: string[];
  poll_interval_seconds?: number;
}
