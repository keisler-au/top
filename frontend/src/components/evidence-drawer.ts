import type { EvidenceItem, TaxonomyType } from "../api/contracts.js";
import { userFacingError } from "../api/errors.js";
import { api, queryStore } from "../app-context.js";
import { formatDateTime } from "../utils/format.js";
import type { UiDialog } from "./ui-dialog.js";

interface EvidenceTarget {
  type: TaxonomyType;
  key: number | string;
  name: string;
}

export class EvidenceDrawer extends HTMLElement {
  readonly #pageSize = 25;
  #dialog: UiDialog | null = null;
  #content: HTMLDivElement | null = null;
  #target: EvidenceTarget | null = null;
  #page = 1;
  #total = 0;
  #items: EvidenceItem[] = [];
  #controller: AbortController | null = null;

  connectedCallback(): void {
    if (this.#dialog) {
      return;
    }
    const dialog = document.createElement("ui-dialog") as UiDialog;
    dialog.setAttribute("heading", "Supporting evidence");
    const content = document.createElement("div");
    content.className = "evidence-drawer-content";
    dialog.append(content);
    this.#dialog = dialog;
    this.#content = content;
    this.append(dialog);
  }

  disconnectedCallback(): void {
    this.#controller?.abort();
  }

  open(type: TaxonomyType, key: number | string, name: string): void {
    this.#target = { type, key, name };
    this.#page = 1;
    this.#total = 0;
    this.#items = [];
    this.#dialog?.setAttribute("heading", `Evidence for ${name}`);
    this.#dialog?.showModal();
    void this.#load(false);
  }

  async #load(append: boolean): Promise<void> {
    const target = this.#target;
    if (!target || !this.#content) {
      return;
    }
    this.#controller?.abort();
    const controller = new AbortController();
    this.#controller = controller;
    if (!append) {
      this.#renderLoading();
    } else {
      this.#setLoadMoreBusy(true);
    }

    const page = this.#page;
    const cacheKey = `evidence:${target.type}:${target.key}:${page}`;
    try {
      const response = await queryStore.fetch(
        cacheKey,
        () => api.evidence(
          target.type,
          target.key,
          page,
          this.#pageSize,
          { signal: controller.signal },
        ),
      );
      if (controller.signal.aborted) {
        return;
      }
      this.#total = response.total;
      this.#items = append
        ? [...this.#items, ...response.items]
        : response.items;
      this.#renderItems();
    } catch (error) {
      if (!controller.signal.aborted) {
        this.#renderError(error, append);
      }
    }
  }

  #renderLoading(): void {
    if (!this.#content) return;
    const loading = document.createElement("ui-loading");
    loading.setAttribute("label", "Loading supporting evidence…");
    this.#content.replaceChildren(loading);
  }

  #renderError(error: unknown, append: boolean): void {
    if (!this.#content) return;
    const alert = document.createElement("ui-alert");
    alert.setAttribute("tone", "danger");
    alert.textContent = userFacingError(error);
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "secondary-button";
    retry.textContent = "Try again";
    retry.addEventListener("click", () => void this.#load(append));
    if (append && this.#items.length > 0) {
      this.#renderItems();
      this.#content.prepend(alert);
      alert.append(document.createElement("br"), retry);
    } else {
      this.#content.replaceChildren(alert, retry);
    }
  }

  #renderItems(): void {
    if (!this.#content) return;
    this.#content.replaceChildren();
    if (this.#items.length === 0) {
      const empty = document.createElement("ui-empty-state");
      const heading = document.createElement("h3");
      heading.textContent = "No evidence available";
      const text = document.createElement("p");
      text.textContent = "The evidence set may have changed since this item loaded.";
      empty.append(heading, text);
      this.#content.append(empty);
      return;
    }

    const summary = document.createElement("p");
    summary.className = "evidence-result-summary";
    summary.textContent = `Showing ${this.#items.length} of ${this.#total} evidence items`;
    const list = document.createElement("ol");
    list.className = "evidence-list";
    for (const item of this.#items) {
      const listItem = document.createElement("li");
      listItem.append(this.#evidenceCard(item));
      list.append(listItem);
    }
    this.#content.append(summary, list);

    if (this.#items.length < this.#total) {
      const loadMore = document.createElement("button");
      loadMore.type = "button";
      loadMore.className = "secondary-button evidence-load-more";
      loadMore.dataset.action = "load-more";
      loadMore.textContent = "Load more evidence";
      loadMore.addEventListener("click", () => {
        this.#page += 1;
        void this.#load(true);
      });
      this.#content.append(loadMore);
    }
  }

  #evidenceCard(item: EvidenceItem): HTMLElement {
    const article = document.createElement("article");
    article.className = "evidence-card";
    const meta = document.createElement("div");
    meta.className = "evidence-card-meta";
    const kind = document.createElement("span");
    kind.className = "evidence-kind";
    kind.textContent = item.type === "segment" ? "System-created segment" : "Original response";
    const date = document.createElement("time");
    date.dateTime = item.created_at;
    date.textContent = formatDateTime(item.created_at);
    meta.append(kind, date);

    const excerpt = document.createElement("blockquote");
    excerpt.textContent = item.excerpt;
    const topic = document.createElement("p");
    topic.className = "evidence-topic";
    topic.textContent = `Topic: ${item.topic_name}`;
    article.append(meta, excerpt, topic);

    if (item.question_context) {
      const question = document.createElement("p");
      question.className = "evidence-context";
      question.textContent = `Question: ${item.question_context.question_text}`;
      article.append(question);
    }

    const sourceParts = [`Source: ${item.source}`];
    if (item.question_context) {
      sourceParts.push(
        `Form: ${item.question_context.form_id ?? item.question_context.form_key}`,
      );
    }
    if (item.submission_key) {
      sourceParts.push(`Submission: ${item.submission_key}`);
    }
    const source = document.createElement("p");
    source.className = "evidence-source";
    source.textContent = sourceParts.join(" · ");
    article.append(source);

    if (item.type === "segment") {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "View untouched original response";
      const original = document.createElement("p");
      original.className = "original-response";
      original.textContent = item.original_text;
      details.append(summary, original);
      article.append(details);
    }
    return article;
  }

  #setLoadMoreBusy(busy: boolean): void {
    const button = this.#content?.querySelector<HTMLButtonElement>(
      '[data-action="load-more"]',
    );
    if (button) {
      button.disabled = busy;
      button.textContent = busy ? "Loading…" : "Load more evidence";
    }
  }
}

customElements.define("evidence-drawer", EvidenceDrawer);
