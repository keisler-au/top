export type TaxonomyType = "theme" | "topic";
export type CoverageState = "no_evidence" | "uncovered" | "covered";
export type EvidenceType = "original" | "segment";
export type RecommendationStrategy = "most-evidence" | "least-covered";
export type GenerationStrategy = "specific" | RecommendationStrategy;
export type GenerationJobStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "dismissed";
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

export interface TemplateVersion {
  id: number;
  version: number;
  html_source: string;
  allowed_placeholders: string[];
  used_by_article_count: number;
  created_by: string | null;
  created_at: string;
}

export interface ArticleTemplate {
  id: number;
  name: string;
  description: string | null;
  status: "active" | "archived";
  versions: TemplateVersion[];
  created_at: string;
  updated_at: string;
}

export interface TemplatePreviewRequest {
  version_id: number;
  title?: string;
  standfirst?: string;
  sections?: Array<Record<string, unknown>>;
}

export interface TemplatePreview {
  rendered_html: string;
}

export interface ArticleTemplateCreate {
  name: string;
  description?: string | null;
  html_source: string;
  created_by?: string | null;
}

export interface ArticleTemplateVersionCreate {
  html_source: string;
  created_by?: string | null;
}

export interface GenerationJobCreate {
  strategy: GenerationStrategy;
  taxonomy_type: TaxonomyType;
  taxonomy_key: string;
  template_version_id: number;
  editorial_guidance?: string | null;
  evidence_ids?: string[];
}

export interface GenerationJob {
  id: number;
  status: GenerationJobStatus;
  strategy: GenerationStrategy;
  taxonomy_type: TaxonomyType;
  taxonomy_key: string;
  taxonomy_name: string;
  template_version_id: number;
  editorial_guidance: string | null;
  attempts: number;
  available_at: string;
  last_error: string | null;
  resulting_article_id: number | null;
  status_url: string;
  created_at: string;
  updated_at: string;
}

export type ArticleStatus = "draft" | "ready_for_review" | "approved" | "archived";
export type ArticleSort = "updated" | "title" | "status";

export interface ArticleTopic {
  name: string;
}

export interface ArticleRevision {
  id: number;
  revision_number: number;
  title: string;
  structured_content: Record<string, unknown>;
  rendered_html: string | null;
  template_version_id: number | null;
  created_at: string;
}

export interface Article {
  id: number;
  title: string;
  status: ArticleStatus;
  current_revision: ArticleRevision;
  generation_metadata: Record<string, unknown> | null;
  theme_ids: number[];
  topics: ArticleTopic[];
  evidence_count: number;
  approved_at: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ArticleQuery {
  status?: ArticleStatus;
  themeId?: number;
  topic?: string;
  search?: string;
  sort?: ArticleSort;
  direction?: SortDirection;
  page?: number;
  pageSize?: number;
}

export interface ArticleEvidenceQuestionContext {
  form_key: string;
  question_key: string;
  question_version: number;
  question_text: string;
}

export interface ArticleEvidence {
  id: number;
  evidence_id: string;
  evidence_order: number;
  citation_id: string | null;
  topic_key: string;
  text: string;
  original_input_id: number;
  evidence_type: EvidenceType;
  original_text: string;
  topic_name: string;
  source: string;
  submission_key: string | null;
  question_context: ArticleEvidenceQuestionContext | null;
}

export interface ArticleAudit {
  id: number;
  revision_id: number | null;
  action: "created" | "revised" | "submitted" | "approved" | "returned_to_draft" | "archived";
  actor: string | null;
  note: string | null;
  created_at: string;
}

export interface ArticlePatch {
  title?: string;
  structured_content?: Record<string, unknown>;
  rendered_html?: string | null;
  theme_ids?: number[];
  topics?: ArticleTopic[];
  expected_revision_id?: number;
}

export interface ArticlePreviewRequest {
  title: string;
  structured_content: Record<string, unknown>;
  expected_revision_id?: number;
}

export interface ArticlePreview {
  rendered_html: string;
}

export interface ArticleTransition {
  note?: string | null;
  actor?: string | null;
}
