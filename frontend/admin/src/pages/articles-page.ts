import type {
  Article,
  ArticleStatus,
  GenerationJob,
  PageResponse,
  TaxonomyItem,
} from "../api/contracts.js";
import { userFacingError } from "../api/errors.js";
import { api, queryStore } from "../app-context.js";
import { formatDateTime, formatInteger } from "../utils/format.js";
import {
  articlesQuery,
  articlesSearch,
  articlesState,
  type ArticlesState,
} from "./articles-state.js";

const statusLabels: Readonly<Record<ArticleStatus, string>> = {
  draft: "Draft",
  ready_for_review: "Ready for review",
  approved: "Approved",
  archived: "Archived",
};

function actionButton(label: string, primary = false): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = primary ? "primary-button" : "secondary-button";
  button.textContent = label;
  return button;
}

export class ArticlesPage extends HTMLElement {
  #state: ArticlesState = articlesState(new URLSearchParams());
  #response: PageResponse<Article> | null = null;
  #failedJobs: PageResponse<GenerationJob> | null = null;
  #themes: TaxonomyItem[] = [];
  #controller: AbortController | null = null;
  #content: HTMLElement | null = null;
  #error: string | null = null;
  #busy = false;

  connectedCallback(): void {
    this.#state = articlesState(new URLSearchParams(window.location.search));
    this.#renderShell();
    void this.#load();
  }

  disconnectedCallback(): void {
    this.#controller?.abort();
  }

  #renderShell(): void {
    this.replaceChildren();
    const header = document.createElement("header");
    header.className = "dashboard-page-header";
    const copy = document.createElement("div");
    copy.className = "page-heading";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "Editorial";
    const heading = document.createElement("h1");
    heading.tabIndex = -1;
    heading.textContent = "Articles";
    const description = document.createElement("p");
    description.className = "page-description";
    description.textContent = "Review drafts, manage approvals, and trace every article to source evidence.";
    copy.append(eyebrow, heading, description);
    const generate = document.createElement("a");
    generate.href = "/generate";
    generate.dataset.route = "";
    generate.className = "primary-link";
    generate.textContent = "Generate article";
    header.append(copy, generate);

    const tabs = document.createElement("nav");
    tabs.className = "article-view-tabs";
    tabs.setAttribute("aria-label", "Article views");
    tabs.append(
      this.#viewLink("Articles", false),
      this.#viewLink("Failed generations", true),
    );

    const filters = document.createElement("section");
    filters.className = "dashboard-panel article-filters";
    filters.setAttribute("aria-labelledby", "article-filter-heading");
    const filterHeading = document.createElement("h2");
    filterHeading.id = "article-filter-heading";
    filterHeading.className = "visually-hidden";
    filterHeading.textContent = "Filter articles";
    filters.append(filterHeading, this.#filterForm());

    const content = document.createElement("section");
    content.className = "dashboard-panel article-library";
    content.setAttribute("aria-live", "polite");
    this.#content = content;
    this.append(header, tabs);
    if (!this.#state.failedGenerations) this.append(filters);
    this.append(content);
    requestAnimationFrame(() => heading.focus());
    this.#renderContent();
  }

  #viewLink(label: string, failed: boolean): HTMLAnchorElement {
    const link = document.createElement("a");
    link.href = failed ? "/articles?generation_status=failed" : "/articles";
    link.dataset.route = "";
    link.textContent = label;
    if (this.#state.failedGenerations === failed) link.setAttribute("aria-current", "page");
    return link;
  }

  #filterForm(): HTMLFormElement {
    const form = document.createElement("form");
    form.className = "article-filter-form";
    const search = this.#input("Search", "search", "search", this.#state.search);
    const status = document.createElement("label");
    status.textContent = "Status";
    const statusSelect = document.createElement("select");
    statusSelect.name = "status";
    const statusOptions: Array<[string, string]> = [
      ["", "All statuses"], ["draft", "Draft"],
      ["ready_for_review", "Ready for review"], ["approved", "Approved"],
      ["archived", "Archived"],
    ];
    for (const [value, label] of statusOptions) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      statusSelect.append(option);
    }
    statusSelect.value = this.#state.status ?? "";
    status.append(statusSelect);

    const theme = document.createElement("label");
    theme.textContent = "Theme";
    const themeSelect = document.createElement("select");
    themeSelect.name = "theme";
    const allThemes = document.createElement("option");
    allThemes.value = "";
    allThemes.textContent = "All themes";
    themeSelect.append(allThemes);
    for (const item of this.#themes) {
      const option = document.createElement("option");
      option.value = String(item.key);
      option.textContent = item.name;
      themeSelect.append(option);
    }
    themeSelect.value = this.#state.themeId === null ? "" : String(this.#state.themeId);
    theme.append(themeSelect);
    const topic = this.#input("Topic", "topic", "text", this.#state.topic);

    const sort = document.createElement("label");
    sort.textContent = "Sort";
    const sortSelect = document.createElement("select");
    sortSelect.name = "sort";
    const sortOptions: Array<[string, string]> = [
      ["updated:desc", "Recently updated"], ["updated:asc", "Oldest updated"],
      ["title:asc", "Title A–Z"], ["title:desc", "Title Z–A"],
      ["status:asc", "Status A–Z"],
    ];
    for (const [value, label] of sortOptions) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      sortSelect.append(option);
    }
    sortSelect.value = `${this.#state.sort}:${this.#state.direction}`;
    sort.append(sortSelect);
    const submit = actionButton("Apply filters", true);
    submit.type = "submit";
    form.append(search, status, theme, topic, sort, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const [sortValue, direction] = String(data.get("sort")).split(":");
      const themeValue = String(data.get("theme") ?? "");
      this.#state = {
        ...this.#state,
        search: String(data.get("search") ?? "").trim(),
        status: (String(data.get("status") || "") || null) as ArticleStatus | null,
        themeId: /^\d+$/.test(themeValue) ? Number.parseInt(themeValue, 10) : null,
        topic: String(data.get("topic") ?? "").trim(),
        sort: sortValue as ArticlesState["sort"],
        direction: direction === "asc" ? "asc" : "desc",
        page: 1,
      };
      this.#replaceUrl();
      void this.#loadArticles();
    });
    return form;
  }

  #input(labelText: string, name: string, type: string, value: string): HTMLLabelElement {
    const label = document.createElement("label");
    label.textContent = labelText;
    const input = document.createElement("input");
    input.name = name;
    input.type = type;
    input.value = value;
    label.append(input);
    return label;
  }

  async #load(): Promise<void> {
    if (this.#state.failedGenerations) {
      await this.#loadFailedJobs();
      return;
    }
    await Promise.allSettled([this.#loadThemes(), this.#loadArticles()]);
  }

  async #loadThemes(): Promise<void> {
    try {
      const response = await api.taxonomy({
        type: "theme", sort: "name", direction: "asc", page: 1, pageSize: 100,
      });
      this.#themes = response.items;
      this.#renderShell();
    } catch {
      // Theme filtering is supplementary; article results remain usable.
    }
  }

  async #loadArticles(): Promise<void> {
    this.#beginLoad();
    try {
      this.#response = await api.articles(
        articlesQuery(this.#state),
        { signal: this.#controller?.signal },
      );
      this.#finishLoad();
    } catch (error) {
      if (!this.#controller?.signal.aborted) this.#finishLoad(userFacingError(error));
    }
  }

  async #loadFailedJobs(): Promise<void> {
    this.#beginLoad();
    try {
      this.#failedJobs = await api.generationJobs(
        "failed", this.#state.page, this.#state.pageSize,
        { signal: this.#controller?.signal },
      );
      this.#finishLoad();
    } catch (error) {
      if (!this.#controller?.signal.aborted) this.#finishLoad(userFacingError(error));
    }
  }

  #beginLoad(): void {
    this.#controller?.abort();
    this.#controller = new AbortController();
    this.#busy = true;
    this.#error = null;
    this.#renderContent();
  }

  #finishLoad(error?: string): void {
    this.#busy = false;
    this.#error = error ?? null;
    this.#renderContent();
  }

  #renderContent(): void {
    if (!this.#content) return;
    this.#content.replaceChildren();
    if (this.#busy) {
      const loading = document.createElement("ui-loading");
      loading.textContent = "Loading editorial work…";
      this.#content.append(loading);
      return;
    }
    if (this.#error) {
      const alert = document.createElement("ui-alert");
      alert.setAttribute("tone", "danger");
      alert.setAttribute("role", "alert");
      alert.textContent = this.#error;
      const retry = actionButton("Try again");
      retry.addEventListener("click", () => void this.#load());
      this.#content.append(alert, retry);
      return;
    }
    if (this.#state.failedGenerations) this.#renderFailedJobs();
    else this.#renderArticles();
  }

  #renderArticles(): void {
    if (!this.#content || !this.#response) return;
    const heading = document.createElement("h2");
    heading.textContent = "Article library";
    const summary = document.createElement("p");
    summary.className = "result-summary";
    summary.textContent = `${formatInteger(this.#response.total)} articles`;
    this.#content.append(heading, summary);
    if (this.#response.items.length === 0) {
      const empty = document.createElement("ui-empty-state");
      empty.textContent = "No articles match these filters.";
      this.#content.append(empty);
    } else {
      const list = document.createElement("ul");
      list.className = "article-list";
      for (const article of this.#response.items) list.append(this.#articleCard(article));
      this.#content.append(list);
    }
    this.#content.append(this.#pagination(this.#response.total));
  }

  #articleCard(article: Article): HTMLLIElement {
    const item = document.createElement("li");
    const body = document.createElement("div");
    const heading = document.createElement("h3");
    const link = document.createElement("a");
    const returnUrl = `${window.location.pathname}${window.location.search}`;
    link.href = `/articles/${article.id}?return=${encodeURIComponent(returnUrl)}`;
    link.dataset.route = "";
    link.textContent = article.title;
    heading.append(link);
    const meta = document.createElement("div");
    meta.className = "article-card-meta";
    const status = document.createElement("ui-status");
    status.setAttribute("tone", article.status === "approved" ? "positive"
      : article.status === "ready_for_review" ? "warning" : "neutral");
    status.textContent = statusLabels[article.status];
    const updated = document.createElement("span");
    updated.textContent = `Updated ${formatDateTime(article.updated_at)}`;
    meta.append(status, updated);
    const tags = document.createElement("p");
    tags.className = "article-tags";
    const names = [
      ...article.theme_ids.map((id) => `Theme #${id}`),
      ...article.topics.map((topic) => topic.name),
    ];
    tags.textContent = names.join(" · ") || "No tags";
    body.append(heading, meta, tags);
    const evidence = document.createElement("strong");
    evidence.textContent = `${formatInteger(article.evidence_count)} evidence`;
    item.append(body, evidence);
    return item;
  }

  #renderFailedJobs(): void {
    if (!this.#content || !this.#failedJobs) return;
    const heading = document.createElement("h2");
    heading.textContent = "Failed generations";
    const summary = document.createElement("p");
    summary.className = "result-summary";
    summary.textContent = `${formatInteger(this.#failedJobs.total)} jobs need attention`;
    this.#content.append(heading, summary);
    if (this.#failedJobs.items.length === 0) {
      const empty = document.createElement("ui-empty-state");
      empty.textContent = "There are no failed generation jobs.";
      this.#content.append(empty);
    } else {
      const list = document.createElement("ul");
      list.className = "failed-generation-list";
      for (const job of this.#failedJobs.items) list.append(this.#failedJob(job));
      this.#content.append(list);
    }
    this.#content.append(this.#pagination(this.#failedJobs.total));
  }

  #failedJob(job: GenerationJob): HTMLLIElement {
    const item = document.createElement("li");
    const copy = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = job.taxonomy_name;
    const meta = document.createElement("p");
    meta.textContent = `Job #${job.id} · ${job.attempts} attempts · ${formatDateTime(job.updated_at)}`;
    const error = document.createElement("p");
    error.className = "generation-error";
    error.textContent = job.last_error ?? "No error detail was recorded.";
    copy.append(heading, meta, error);
    const actions = document.createElement("div");
    actions.className = "row-actions";
    const open = document.createElement("a");
    open.href = `/generate?job=${job.id}`;
    open.dataset.route = "";
    open.className = "secondary-button";
    open.textContent = "Inspect";
    const retry = actionButton("Retry", true);
    retry.addEventListener("click", () => void this.#retryJob(job.id));
    actions.append(open, retry);
    item.append(copy, actions);
    return item;
  }

  async #retryJob(id: number): Promise<void> {
    try {
      await api.retryGenerationJob(id);
      queryStore.invalidate("dashboard:summary");
      await this.#loadFailedJobs();
    } catch (error) {
      this.#error = userFacingError(error);
      this.#renderContent();
    }
  }

  #pagination(total: number): HTMLElement {
    const nav = document.createElement("nav");
    nav.className = "pagination";
    nav.setAttribute("aria-label", "Article pages");
    const pages = Math.max(1, Math.ceil(total / this.#state.pageSize));
    const previous = actionButton("Previous");
    previous.disabled = this.#state.page <= 1;
    previous.addEventListener("click", () => this.#changePage(this.#state.page - 1));
    const label = document.createElement("span");
    label.textContent = `Page ${this.#state.page} of ${pages}`;
    const next = actionButton("Next");
    next.disabled = this.#state.page >= pages;
    next.addEventListener("click", () => this.#changePage(this.#state.page + 1));
    nav.append(previous, label, next);
    return nav;
  }

  #changePage(page: number): void {
    this.#state.page = page;
    this.#replaceUrl();
    void (this.#state.failedGenerations ? this.#loadFailedJobs() : this.#loadArticles());
  }

  #replaceUrl(): void {
    window.history.replaceState({}, "", `/articles?${articlesSearch(this.#state)}`);
  }
}

customElements.define("articles-page", ArticlesPage);
