import type {
  DashboardSummary,
  RecommendationItem,
  RecommendationStrategy,
  TaxonomyItem,
} from "../api/contracts.js";
import { userFacingError } from "../api/errors.js";
import { api, queryStore } from "../app-context.js";
import type { EvidenceDrawer } from "../components/evidence-drawer.js";
import { formatInteger } from "../utils/format.js";
import {
  dashboardState,
  generationUrl,
  pageCount,
  stateAsQuery,
  stateAsSearch,
  type DashboardState,
} from "./dashboard-state.js";

type DashboardView = "overview" | "taxonomy";

export class DashboardOverview extends HTMLElement {
  #state: DashboardState = dashboardState(new URLSearchParams());
  #summaryController: AbortController | null = null;
  #taxonomyController: AbortController | null = null;
  #recommendationController: AbortController | null = null;
  #coverageContent: HTMLElement | null = null;
  #pagination: HTMLElement | null = null;
  #recommendations: HTMLElement | null = null;
  #summaryContent: HTMLElement | null = null;
  #attentionContent: HTMLElement | null = null;
  #drawer: EvidenceDrawer | null = null;
  #searchInput: HTMLInputElement | null = null;
  #sortSelect: HTMLSelectElement | null = null;
  #typeButtons: HTMLButtonElement[] = [];

  connectedCallback(): void {
    this.#state = dashboardState(new URLSearchParams(window.location.search));
    this.#renderShell();
    void this.#loadInitialData();
  }

  disconnectedCallback(): void {
    this.#summaryController?.abort();
    this.#taxonomyController?.abort();
    this.#recommendationController?.abort();
  }

  get #view(): DashboardView {
    return this.getAttribute("view") === "taxonomy" ? "taxonomy" : "overview";
  }

  async #loadInitialData(): Promise<void> {
    const requests: Promise<void>[] = [this.#loadTaxonomy()];
    if (this.#view === "overview") {
      requests.push(this.#loadSummary(), this.#loadRecommendations());
    }
    await Promise.allSettled(requests);
  }

  #renderShell(): void {
    this.replaceChildren();
    const pageHeader = this.#pageHeader();
    this.append(pageHeader);

    if (this.#view === "overview") {
      const summary = document.createElement("section");
      summary.className = "dashboard-summary";
      summary.setAttribute("aria-labelledby", "summary-heading");
      const heading = document.createElement("h2");
      heading.id = "summary-heading";
      heading.className = "visually-hidden";
      heading.textContent = "Dashboard summary";
      const content = document.createElement("div");
      content.className = "metric-grid";
      this.#summaryContent = content;
      summary.append(heading, content);
      this.append(summary);
      this.#renderSectionLoading(content, "Loading dashboard summary…");
    }

    this.append(this.#coverageSection());

    if (this.#view === "overview") {
      const lowerGrid = document.createElement("div");
      lowerGrid.className = "dashboard-lower-grid";
      const recommendations = document.createElement("section");
      recommendations.className = "dashboard-panel recommendations-panel";
      recommendations.setAttribute("aria-labelledby", "recommendations-heading");
      const recommendationHeading = document.createElement("h2");
      recommendationHeading.id = "recommendations-heading";
      recommendationHeading.textContent = "Recommended opportunities";
      const recommendationContent = document.createElement("div");
      recommendationContent.className = "recommendation-grid";
      this.#recommendations = recommendationContent;
      recommendations.append(recommendationHeading, recommendationContent);
      this.#renderSectionLoading(recommendationContent, "Loading recommendations…");

      const attention = document.createElement("section");
      attention.className = "dashboard-panel attention-panel";
      attention.setAttribute("aria-labelledby", "attention-heading");
      const attentionHeading = document.createElement("h2");
      attentionHeading.id = "attention-heading";
      attentionHeading.textContent = "Needs attention";
      const attentionContent = document.createElement("div");
      this.#attentionContent = attentionContent;
      attention.append(attentionHeading, attentionContent);
      this.#renderSectionLoading(attentionContent, "Checking editorial work…");
      lowerGrid.append(recommendations, attention);
      this.append(lowerGrid);
    }

    const drawer = document.createElement("evidence-drawer") as EvidenceDrawer;
    this.#drawer = drawer;
    this.append(drawer);
  }

  #pageHeader(): HTMLElement {
    const header = document.createElement("header");
    header.className = "dashboard-page-header";
    const copy = document.createElement("div");
    copy.className = "page-heading";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = this.#view === "overview" ? "Dashboard" : "Explore";
    const heading = document.createElement("h1");
    heading.tabIndex = -1;
    heading.textContent = this.#view === "overview"
      ? "Evidence overview"
      : "Themes and topics";
    const description = document.createElement("p");
    description.className = "page-description";
    description.textContent = this.#view === "overview"
      ? "Find well-supported stories and see where approved article coverage is missing."
      : "Explore classifications, coverage, and the original evidence behind them.";
    copy.append(eyebrow, heading, description);
    header.append(copy);
    if (this.#view === "overview") {
      const generate = document.createElement("a");
      generate.href = "/generate";
      generate.dataset.route = "";
      generate.className = "primary-link";
      generate.textContent = "Generate article";
      header.append(generate);
    }
    requestAnimationFrame(() => heading.focus());
    return header;
  }

  #coverageSection(): HTMLElement {
    const section = document.createElement("section");
    section.className = "dashboard-panel coverage-panel";
    section.setAttribute("aria-labelledby", "coverage-heading");
    const header = document.createElement("div");
    header.className = "panel-heading-row";
    const headingGroup = document.createElement("div");
    const heading = document.createElement("h2");
    heading.id = "coverage-heading";
    heading.textContent = "Coverage";
    const description = document.createElement("p");
    description.textContent = "Compare supporting evidence with article coverage.";
    headingGroup.append(heading, description);
    header.append(headingGroup, this.#typeSwitch());

    const toolbar = document.createElement("div");
    toolbar.className = "coverage-toolbar";
    const form = document.createElement("form");
    form.className = "search-form";
    form.setAttribute("role", "search");
    const label = document.createElement("label");
    label.htmlFor = "taxonomy-search";
    label.className = "visually-hidden";
    label.textContent = "Search themes and topics";
    const input = document.createElement("input");
    input.id = "taxonomy-search";
    input.type = "search";
    input.placeholder = `Search ${this.#state.type === "theme" ? "themes" : "topics"}`;
    input.value = this.#state.search;
    input.autocomplete = "off";
    this.#searchInput = input;
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "secondary-button";
    submit.textContent = "Search";
    form.append(label, input, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      this.#changeState({ search: input.value.trim(), page: 1 });
    });

    const sortLabel = document.createElement("label");
    sortLabel.className = "sort-control";
    const sortText = document.createElement("span");
    sortText.textContent = "Sort by";
    const select = document.createElement("select");
    select.setAttribute("aria-label", "Sort coverage");
    const sortOptions = [
      ["evidence:desc", "Most evidence"],
      ["evidence:asc", "Least evidence"],
      ["approved_articles:asc", "Least approved coverage"],
      ["approved_articles:desc", "Most approved coverage"],
      ["articles:asc", "Fewest articles"],
      ["articles:desc", "Most articles"],
      ["name:asc", "Name A–Z"],
      ["name:desc", "Name Z–A"],
    ] as const;
    for (const [value, text] of sortOptions) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = text;
      select.append(option);
    }
    select.value = `${this.#state.sort}:${this.#state.direction}`;
    select.addEventListener("change", () => {
      const [sort, direction] = select.value.split(":");
      if (sort && direction) {
        this.#changeState({
          sort: sort as DashboardState["sort"],
          direction: direction as DashboardState["direction"],
          page: 1,
        });
      }
    });
    this.#sortSelect = select;
    sortLabel.append(sortText, select);
    toolbar.append(form, sortLabel);

    const content = document.createElement("div");
    content.className = "coverage-content";
    content.setAttribute("aria-live", "polite");
    this.#coverageContent = content;
    this.#renderSectionLoading(content, "Loading coverage…");
    const pagination = document.createElement("nav");
    pagination.className = "pagination";
    pagination.setAttribute("aria-label", "Coverage pages");
    this.#pagination = pagination;
    section.append(header, toolbar, content, pagination);
    return section;
  }

  #typeSwitch(): HTMLElement {
    const group = document.createElement("div");
    group.className = "segmented-control";
    group.setAttribute("aria-label", "Taxonomy type");
    for (const [type, label] of [["theme", "Themes"], ["topic", "Topics"]] as const) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.dataset.type = type;
      button.setAttribute("aria-pressed", String(this.#state.type === type));
      button.addEventListener("click", () => {
        if (type !== this.#state.type) {
          this.#changeState({ type, page: 1 });
        }
      });
      this.#typeButtons.push(button);
      group.append(button);
    }
    return group;
  }

  #changeState(changes: Partial<DashboardState>): void {
    const typeChanged = changes.type !== undefined && changes.type !== this.#state.type;
    this.#state = { ...this.#state, ...changes };
    const url = `${window.location.pathname}?${stateAsSearch(this.#state)}`;
    window.history.replaceState({}, "", url);
    this.#synchronizeControls();
    void this.#loadTaxonomy();
    if (typeChanged && this.#view === "overview") {
      void this.#loadRecommendations();
    }
  }

  #synchronizeControls(): void {
    if (this.#searchInput) {
      this.#searchInput.value = this.#state.search;
      const taxonomyLabel = this.#state.type === "theme" ? "themes" : "topics";
      this.#searchInput.placeholder = `Search ${taxonomyLabel}`;
    }
    if (this.#sortSelect) {
      this.#sortSelect.value = `${this.#state.sort}:${this.#state.direction}`;
    }
    for (const button of this.#typeButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.type === this.#state.type));
    }
  }

  async #loadSummary(): Promise<void> {
    if (!this.#summaryContent) return;
    this.#summaryController?.abort();
    const controller = new AbortController();
    this.#summaryController = controller;
    try {
      const summary = await queryStore.fetch(
        "dashboard:summary",
        () => api.summary({ signal: controller.signal }),
      );
      if (!controller.signal.aborted) {
        this.#renderSummary(summary);
        this.#renderAttention(summary);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        this.#renderError(this.#summaryContent, error, () => void this.#loadSummary());
        if (this.#attentionContent) {
          this.#renderError(this.#attentionContent, error, () => void this.#loadSummary());
        }
      }
    }
  }

  #renderSummary(summary: DashboardSummary): void {
    if (!this.#summaryContent) return;
    const metrics = [
      ["Evidence", summary.evidence_count, "Classified source points"],
      ["Themes", summary.theme_count, "Canonical live themes"],
      ["Topics", summary.topic_count, "Topics with evidence"],
      ["Articles", summary.article_count, "Active articles"],
      ["Awaiting approval", summary.awaiting_approval_count, "Ready for review"],
    ] as const;
    this.#summaryContent.replaceChildren();
    for (const [label, value, description] of metrics) {
      const article = document.createElement("article");
      article.className = "metric-card";
      const metricLabel = document.createElement("p");
      metricLabel.className = "metric-label";
      metricLabel.textContent = label;
      const metricValue = document.createElement("p");
      metricValue.className = "metric-value";
      metricValue.textContent = formatInteger(value);
      const metricDescription = document.createElement("p");
      metricDescription.className = "metric-description";
      metricDescription.textContent = description;
      article.append(metricLabel, metricValue, metricDescription);
      this.#summaryContent.append(article);
    }
  }

  #renderAttention(summary: DashboardSummary): void {
    if (!this.#attentionContent) return;
    this.#attentionContent.replaceChildren();
    if (
      summary.awaiting_approval_count === 0
      && summary.failed_generation_count === 0
    ) {
      const status = document.createElement("ui-status");
      status.setAttribute("tone", "positive");
      status.setAttribute("role", "status");
      status.textContent = "Nothing needs attention";
      const text = document.createElement("p");
      text.className = "attention-copy";
      text.textContent = "There are no articles awaiting approval or failed generation jobs.";
      this.#attentionContent.append(status, text);
      return;
    }
    const list = document.createElement("ul");
    list.className = "attention-list";
    if (summary.awaiting_approval_count > 0) {
      list.append(this.#attentionItem(
        `${formatInteger(summary.awaiting_approval_count)} awaiting approval`,
        "/articles?status=ready_for_review",
      ));
    }
    if (summary.failed_generation_count > 0) {
      list.append(this.#attentionItem(
        `${formatInteger(summary.failed_generation_count)} failed generations`,
        "/articles?generation_status=failed",
      ));
    }
    this.#attentionContent.append(list);
  }

  #attentionItem(label: string, href: string): HTMLLIElement {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = href;
    link.dataset.route = "";
    link.textContent = label;
    item.append(link);
    return item;
  }

  async #loadTaxonomy(): Promise<void> {
    if (!this.#coverageContent) return;
    this.#taxonomyController?.abort();
    const controller = new AbortController();
    this.#taxonomyController = controller;
    this.#renderSectionLoading(this.#coverageContent, "Loading coverage…");
    this.#pagination?.replaceChildren();
    const query = stateAsQuery(this.#state);
    const cacheKey = `taxonomy:${stateAsSearch(this.#state)}`;
    try {
      const response = await queryStore.fetch(
        cacheKey,
        () => api.taxonomy(query, { signal: controller.signal }),
      );
      if (controller.signal.aborted) return;
      const pages = pageCount(response.total, response.page_size);
      if (response.page > pages) {
        this.#changeState({ page: pages });
        return;
      }
      this.#renderTaxonomy(response.items, response.total);
      this.#renderPagination(response.total);
    } catch (error) {
      if (!controller.signal.aborted) {
        this.#renderError(this.#coverageContent, error, () => void this.#loadTaxonomy());
      }
    }
  }

  #renderTaxonomy(items: TaxonomyItem[], total: number): void {
    if (!this.#coverageContent) return;
    this.#coverageContent.replaceChildren();
    if (items.length === 0) {
      const empty = document.createElement("ui-empty-state");
      const heading = document.createElement("h3");
      heading.textContent = this.#state.search
        ? "No matching results"
        : `No ${this.#state.type === "theme" ? "themes" : "topics"} yet`;
      const text = document.createElement("p");
      text.textContent = this.#state.search
        ? "Try a different search term or clear the search."
        : "Completed classified evidence will appear here.";
      empty.append(heading, text);
      this.#coverageContent.append(empty);
      return;
    }

    const resultSummary = document.createElement("p");
    resultSummary.className = "result-summary";
    const taxonomyLabel = this.#state.type === "theme" ? "themes" : "topics";
    resultSummary.textContent = `${formatInteger(total)} ${taxonomyLabel}`;
    const tableWrapper = document.createElement("div");
    tableWrapper.className = "coverage-table-wrapper";
    const table = document.createElement("table");
    table.className = "coverage-table";
    const caption = document.createElement("caption");
    caption.className = "visually-hidden";
    const captionType = this.#state.type === "theme" ? "Theme" : "Topic";
    caption.textContent = `${captionType} evidence and article coverage`;
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    const columns = [
      ["Name", "name"],
      ["Evidence", "evidence"],
      ["Articles", "articles"],
      ["Coverage", "approved_articles"],
      ["Actions", null],
    ] as const;
    for (const [label, sort] of columns) {
      const cell = document.createElement("th");
      cell.scope = "col";
      if (sort) {
        const active = this.#state.sort === sort;
        if (active) {
          cell.setAttribute(
            "aria-sort",
            this.#state.direction === "asc" ? "ascending" : "descending",
          );
        }
        const button = document.createElement("button");
        button.type = "button";
        button.className = "sort-header";
        button.textContent = label;
        if (active) {
          const indicator = document.createElement("span");
          indicator.setAttribute("aria-hidden", "true");
          indicator.textContent = this.#state.direction === "asc" ? "↑" : "↓";
          button.append(indicator);
        }
        button.addEventListener("click", () => this.#sortBy(sort));
        cell.append(button);
      } else {
        cell.textContent = label;
      }
      headRow.append(cell);
    }
    head.append(headRow);
    const body = document.createElement("tbody");
    for (const item of items) {
      body.append(this.#taxonomyRow(item));
    }
    table.append(caption, head, body);
    tableWrapper.append(table);
    this.#coverageContent.append(resultSummary, tableWrapper);
  }

  #taxonomyRow(item: TaxonomyItem): HTMLTableRowElement {
    const row = document.createElement("tr");
    const nameCell = document.createElement("th");
    nameCell.scope = "row";
    nameCell.dataset.label = "Name";
    const name = document.createElement("span");
    name.className = "taxonomy-name";
    name.textContent = item.name;
    nameCell.append(name);
    if (item.description) {
      const description = document.createElement("span");
      description.className = "taxonomy-description";
      description.textContent = item.description;
      nameCell.append(description);
    }

    const evidenceCell = document.createElement("td");
    evidenceCell.dataset.label = "Evidence";
    evidenceCell.textContent = formatInteger(item.evidence_count);
    const articleCell = document.createElement("td");
    articleCell.dataset.label = "Articles";
    const articleCount = document.createElement("span");
    articleCount.textContent = formatInteger(item.article_count);
    const approved = document.createElement("small");
    approved.textContent = `${formatInteger(item.approved_article_count)} approved`;
    articleCell.append(articleCount, approved);

    const coverageCell = document.createElement("td");
    coverageCell.dataset.label = "Coverage";
    coverageCell.append(this.#coverageStatus(item));

    const actionsCell = document.createElement("td");
    actionsCell.dataset.label = "Actions";
    const actions = document.createElement("div");
    actions.className = "row-actions";
    const evidence = document.createElement("button");
    evidence.type = "button";
    evidence.className = "quiet-button";
    evidence.textContent = "View evidence";
    evidence.disabled = item.evidence_count === 0;
    evidence.addEventListener("click", () => {
      this.#drawer?.open(item.type, item.key, item.name);
    });
    actions.append(evidence);
    if (item.generation_eligible) {
      actions.append(this.#generateLink(item));
    }
    actionsCell.append(actions);
    row.append(nameCell, evidenceCell, articleCell, coverageCell, actionsCell);
    return row;
  }

  #sortBy(sort: DashboardState["sort"]): void {
    const defaultDirections: Record<DashboardState["sort"], DashboardState["direction"]> = {
      name: "asc",
      evidence: "desc",
      articles: "asc",
      approved_articles: "asc",
    };
    const direction = this.#state.sort === sort
      ? (this.#state.direction === "asc" ? "desc" : "asc")
      : defaultDirections[sort];
    this.#changeState({ sort, direction, page: 1 });
  }

  #coverageStatus(item: TaxonomyItem): HTMLElement {
    const status = document.createElement("ui-status");
    const labels = {
      no_evidence: "No evidence",
      uncovered: "Uncovered",
      covered: "Covered",
    } as const;
    status.textContent = labels[item.coverage_state];
    if (item.coverage_state === "covered") status.setAttribute("tone", "positive");
    if (item.coverage_state === "uncovered") status.setAttribute("tone", "warning");
    return status;
  }

  #generateLink(item: TaxonomyItem): HTMLAnchorElement {
    const link = document.createElement("a");
    link.href = generationUrl(item.type, item.key, item.name);
    link.dataset.route = "";
    link.className = "compact-primary-link";
    link.textContent = "Generate";
    link.setAttribute("aria-label", `Generate an article for ${item.name}`);
    return link;
  }

  #renderPagination(total: number): void {
    if (!this.#pagination) return;
    this.#pagination.replaceChildren();
    const pages = pageCount(total, this.#state.pageSize);
    if (pages <= 1) return;
    const previous = document.createElement("button");
    previous.type = "button";
    previous.className = "secondary-button";
    previous.textContent = "Previous";
    previous.disabled = this.#state.page <= 1;
    previous.addEventListener("click", () => this.#changePage(this.#state.page - 1));
    const status = document.createElement("span");
    status.textContent = `Page ${this.#state.page} of ${pages}`;
    status.setAttribute("aria-current", "page");
    const next = document.createElement("button");
    next.type = "button";
    next.className = "secondary-button";
    next.textContent = "Next";
    next.disabled = this.#state.page >= pages;
    next.addEventListener("click", () => this.#changePage(this.#state.page + 1));
    this.#pagination.append(previous, status, next);
  }

  #changePage(page: number): void {
    this.#changeState({ page });
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.querySelector("#coverage-heading")?.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "start",
    });
  }

  async #loadRecommendations(): Promise<void> {
    if (!this.#recommendations) return;
    this.#recommendationController?.abort();
    const controller = new AbortController();
    this.#recommendationController = controller;
    this.#renderSectionLoading(this.#recommendations, "Loading recommendations…");
    try {
      const [most, least] = await Promise.all([
        queryStore.fetch(
          `recommendations:${this.#state.type}:most-evidence`,
          () => api.recommendations(
            this.#state.type,
            "most-evidence",
            3,
            { signal: controller.signal },
          ),
        ),
        queryStore.fetch(
          `recommendations:${this.#state.type}:least-covered`,
          () => api.recommendations(
            this.#state.type,
            "least-covered",
            3,
            { signal: controller.signal },
          ),
        ),
      ]);
      if (!controller.signal.aborted) {
        this.#renderRecommendations(most.items, least.items);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        this.#renderError(this.#recommendations, error, () => void this.#loadRecommendations());
      }
    }
  }

  #renderRecommendations(
    mostEvidence: RecommendationItem[],
    leastCovered: RecommendationItem[],
  ): void {
    if (!this.#recommendations) return;
    this.#recommendations.replaceChildren(
      this.#recommendationGroup("Most evidence", "most-evidence", mostEvidence),
      this.#recommendationGroup("Least covered", "least-covered", leastCovered),
    );
  }

  #recommendationGroup(
    title: string,
    strategy: RecommendationStrategy,
    items: RecommendationItem[],
  ): HTMLElement {
    const group = document.createElement("section");
    group.className = "recommendation-group";
    const heading = document.createElement("h3");
    heading.textContent = title;
    group.append(heading);
    if (items.length === 0) {
      const empty = document.createElement("p");
      empty.className = "muted-copy";
      empty.textContent = "No eligible evidence yet.";
      group.append(empty);
      return group;
    }
    const list = document.createElement("ol");
    list.className = "recommendation-list";
    for (const item of items) {
      const listItem = document.createElement("li");
      const itemHeading = document.createElement("h4");
      itemHeading.textContent = item.name;
      const explanation = document.createElement("p");
      explanation.textContent = item.explanation;
      const actions = document.createElement("div");
      actions.className = "row-actions";
      const evidence = document.createElement("button");
      evidence.type = "button";
      evidence.className = "quiet-button";
      evidence.textContent = "Evidence";
      evidence.addEventListener("click", () => {
        this.#drawer?.open(item.type, item.key, item.name);
      });
      const generate = this.#generateLink(item);
      generate.href = generationUrl(item.type, item.key, item.name, strategy);
      actions.append(evidence, generate);
      listItem.append(itemHeading, explanation, actions);
      list.append(listItem);
    }
    group.append(list);
    return group;
  }

  #renderSectionLoading(container: HTMLElement, label: string): void {
    const loading = document.createElement("ui-loading");
    loading.setAttribute("label", label);
    container.replaceChildren(loading);
  }

  #renderError(container: HTMLElement, error: unknown, retryAction: () => void): void {
    const alert = document.createElement("ui-alert");
    alert.setAttribute("tone", "danger");
    alert.textContent = userFacingError(error);
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "secondary-button";
    retry.textContent = "Try again";
    retry.addEventListener("click", retryAction);
    container.replaceChildren(alert, retry);
  }
}

customElements.define("dashboard-overview", DashboardOverview);
