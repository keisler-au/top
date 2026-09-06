import type {
  Article,
  ArticleAudit,
  ArticleEvidence,
  ArticleStatus,
} from "../api/contracts.js";
import { ApiError, userFacingError } from "../api/errors.js";
import { api, queryStore } from "../app-context.js";
import type { UiDialog } from "../components/ui-dialog.js";
import { formatDateTime, formatInteger } from "../utils/format.js";
import {
  editableArticleContent,
  paragraphsFromText,
  parseThemeIds,
  parseTopicNames,
  type EditableArticleContent,
} from "./article-detail-state.js";
import { articleReturnUrl } from "./articles-state.js";

const statusLabels: Readonly<Record<ArticleStatus, string>> = {
  draft: "Draft",
  ready_for_review: "Ready for review",
  approved: "Approved",
  archived: "Archived",
};

const auditLabels: Readonly<Record<ArticleAudit["action"], string>> = {
  created: "Article created",
  revised: "Revision saved",
  submitted: "Submitted for review",
  approved: "Approved",
  returned_to_draft: "Returned to draft",
  archived: "Archived",
};

function button(label: string, primary = false): HTMLButtonElement {
  const element = document.createElement("button");
  element.type = "button";
  element.className = primary ? "primary-button" : "secondary-button";
  element.textContent = label;
  return element;
}

export class ArticleDetailPage extends HTMLElement {
  #articleId: number | null = null;
  #article: Article | null = null;
  #evidence: ArticleEvidence[] = [];
  #history: ArticleAudit[] = [];
  #content: EditableArticleContent | null = null;
  #title = "";
  #themeIds = "";
  #topics = "";
  #previewHtml: string | null = null;
  #controller: AbortController | null = null;
  #busy = true;
  #saving = false;
  #dirty = false;
  #conflict = false;
  #error: string | null = null;
  #live: HTMLElement | null = null;

  connectedCallback(): void {
    const value = this.getAttribute("article-id") ?? "";
    this.#articleId = /^\d+$/.test(value) && Number(value) > 0 ? Number(value) : null;
    window.addEventListener("beforeunload", this.#beforeUnload);
    this.#render();
    if (this.#articleId !== null) void this.#load();
  }

  disconnectedCallback(): void {
    window.removeEventListener("beforeunload", this.#beforeUnload);
    this.#controller?.abort();
  }

  readonly #beforeUnload = (event: BeforeUnloadEvent): void => {
    if (!this.#dirty) return;
    event.preventDefault();
  };

  async #load(): Promise<void> {
    if (this.#articleId === null) return;
    this.#controller?.abort();
    const controller = new AbortController();
    this.#controller = controller;
    this.#busy = true;
    this.#error = null;
    this.#render();
    try {
      const [article, evidence, history] = await Promise.all([
        api.article(this.#articleId, { signal: controller.signal }),
        api.articleEvidence(this.#articleId, { signal: controller.signal }),
        api.articleHistory(this.#articleId, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted) return;
      this.#article = article;
      this.#evidence = evidence;
      this.#history = history;
      this.#title = article.current_revision.title;
      this.#content = editableArticleContent(article.current_revision.structured_content);
      this.#themeIds = article.theme_ids.join(", ");
      this.#topics = article.topics.map((topic) => topic.name).join("\n");
      this.#previewHtml = article.current_revision.rendered_html;
      this.#dirty = false;
      this.#conflict = false;
      this.#busy = false;
      this.#render();
    } catch (error) {
      if (!controller.signal.aborted) {
        this.#busy = false;
        this.#error = userFacingError(error);
        this.#render();
      }
    }
  }

  #render(): void {
    this.replaceChildren();
    const live = document.createElement("p");
    live.className = "visually-hidden";
    live.setAttribute("aria-live", "polite");
    this.#live = live;
    if (this.#articleId === null) {
      this.append(this.#errorState("This article URL is invalid."), live);
      return;
    }
    if (this.#busy) {
      const loading = document.createElement("ui-loading");
      loading.textContent = "Loading article workspace…";
      this.append(loading, live);
      return;
    }
    if (!this.#article) {
      this.append(this.#errorState(this.#error ?? "The article could not be loaded."), live);
      return;
    }
    this.append(this.#header(), this.#workspace(), live);
  }

  #errorState(message: string): HTMLElement {
    const panel = document.createElement("section");
    panel.className = "dashboard-panel article-error-state";
    const alert = document.createElement("ui-alert");
    alert.setAttribute("tone", "danger");
    alert.setAttribute("role", "alert");
    alert.textContent = message;
    const actions = document.createElement("div");
    actions.className = "row-actions";
    if (this.#articleId !== null) {
      const retry = button("Try again", true);
      retry.addEventListener("click", () => void this.#load());
      actions.append(retry);
    }
    const back = document.createElement("a");
    back.href = "/articles";
    back.dataset.route = "";
    back.className = "secondary-button";
    back.textContent = "Back to articles";
    actions.append(back);
    panel.append(alert, actions);
    return panel;
  }

  #header(): HTMLElement {
    const article = this.#article!;
    const header = document.createElement("header");
    header.className = "dashboard-page-header article-workspace-heading";
    const copy = document.createElement("div");
    copy.className = "page-heading";
    const back = document.createElement("a");
    back.href = articleReturnUrl(new URLSearchParams(window.location.search));
    back.dataset.route = "";
    back.className = "back-link";
    back.textContent = "← Back to articles";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = `Revision ${article.current_revision.revision_number}`;
    const heading = document.createElement("h1");
    heading.tabIndex = -1;
    heading.textContent = article.title;
    const meta = document.createElement("div");
    meta.className = "article-heading-meta";
    const status = document.createElement("ui-status");
    status.setAttribute("tone", article.status === "approved" ? "positive"
      : article.status === "ready_for_review" ? "warning" : "neutral");
    status.textContent = statusLabels[article.status];
    const updated = document.createElement("span");
    updated.textContent = `Updated ${formatDateTime(article.updated_at)}`;
    meta.append(status, updated);
    copy.append(back, eyebrow, heading, meta);
    header.append(copy, this.#lifecycleActions());
    requestAnimationFrame(() => heading.focus());
    return header;
  }

  #lifecycleActions(): HTMLElement {
    const actions = document.createElement("div");
    actions.className = "article-lifecycle-actions";
    const status = this.#article!.status;
    if (status === "draft") {
      const submit = button("Submit for review", true);
      submit.disabled = this.#saving;
      submit.addEventListener("click", () => void this.#submitForReview());
      actions.append(submit);
    } else if (status === "ready_for_review") {
      const approve = button("Approve article", true);
      approve.addEventListener("click", () => this.#confirmTransition(
        "Approve this revision?",
        "This revision will become approved coverage. Its evidence and rendered preview will remain auditable.",
        "Approve article",
        "approve",
      ));
      const draft = button("Return to draft");
      draft.addEventListener("click", () => void this.#transition("return-to-draft"));
      actions.append(approve, draft);
    } else if (status === "approved") {
      const draft = button("Create editable draft", true);
      draft.addEventListener("click", () => void this.#transition("return-to-draft"));
      actions.append(draft);
    }
    if (status !== "archived") {
      const archive = button("Archive");
      archive.addEventListener("click", () => this.#confirmTransition(
        "Archive this article?",
        "Archived articles no longer count toward active coverage.",
        "Archive article",
        "archive",
      ));
      actions.append(archive);
    }
    return actions;
  }

  #workspace(): HTMLElement {
    const layout = document.createElement("div");
    layout.className = "article-workspace-layout";
    const main = document.createElement("div");
    main.className = "article-workspace-main";
    if (this.#error) {
      const alert = document.createElement("ui-alert");
      alert.setAttribute("tone", "danger");
      alert.setAttribute("role", "alert");
      alert.textContent = this.#error;
      main.append(alert);
      if (this.#conflict) {
        const reload = button("Reload latest revision");
        reload.addEventListener("click", () => void this.#load());
        main.append(reload);
      }
    }
    if (this.#article!.status === "draft") main.append(this.#editor());
    else main.append(this.#readOnlyNotice());
    main.append(this.#preview());
    const aside = document.createElement("aside");
    aside.className = "article-workspace-aside";
    aside.append(this.#evidencePanel(), this.#historyPanel());
    layout.append(main, aside);
    return layout;
  }

  #readOnlyNotice(): HTMLElement {
    const panel = document.createElement("section");
    panel.className = "dashboard-panel";
    const heading = document.createElement("h2");
    heading.textContent = "Revision is read-only";
    const copy = document.createElement("p");
    copy.textContent = this.#article!.status === "approved"
      ? "Approved content cannot be overwritten. Create an editable draft to make a new revision."
      : this.#article!.status === "archived"
        ? "Archived articles cannot be edited."
        : "Return this article to draft before making changes.";
    panel.append(heading, copy);
    return panel;
  }

  #editor(): HTMLElement {
    const content = this.#content!;
    const panel = document.createElement("section");
    panel.className = "dashboard-panel article-editor";
    const heading = document.createElement("h2");
    heading.textContent = "Structured content";
    const help = document.createElement("p");
    help.className = "muted-copy";
    help.textContent = "Edit article fields and sections. Saving renders the selected template on the server first.";
    const form = document.createElement("form");
    form.className = "article-editor-form";
    const title = this.#textField("Article title", this.#title, 500);
    title.input.addEventListener("input", () => {
      this.#title = title.input.value;
      this.#markDirty();
    });
    const standfirst = this.#textareaField("Standfirst", content.standfirst, 1000, 3);
    standfirst.input.addEventListener("input", () => {
      content.standfirst = standfirst.input.value;
      this.#markDirty();
    });
    form.append(title.field, standfirst.field);
    const sectionHeading = document.createElement("h3");
    sectionHeading.textContent = "Sections";
    form.append(sectionHeading);
    content.sections.forEach((section, index) => form.append(this.#sectionEditor(index)));
    const add = button("Add section");
    add.addEventListener("click", () => {
      content.sections.push({ heading: "", paragraphs: [""] });
      this.#markDirty();
      this.#render();
    });
    const tags = document.createElement("fieldset");
    const legend = document.createElement("legend");
    legend.textContent = "Taxonomy tags";
    const themes = this.#textField("Theme IDs", this.#themeIds, 500);
    themes.input.placeholder = "For example: 2, 7";
    themes.input.addEventListener("input", () => {
      this.#themeIds = themes.input.value;
      this.#markDirty();
    });
    const topics = this.#textareaField("Topics", this.#topics, 2000, 4);
    topics.input.placeholder = "One topic per line";
    topics.input.addEventListener("input", () => {
      this.#topics = topics.input.value;
      this.#markDirty();
    });
    tags.append(legend, themes.field, topics.field);
    const actions = document.createElement("div");
    actions.className = "generation-actions";
    const preview = button("Refresh preview");
    preview.disabled = this.#saving;
    preview.addEventListener("click", () => void this.#refreshPreview());
    const save = button(this.#saving ? "Saving…" : "Save revision", true);
    save.dataset.action = "save-article";
    save.disabled = this.#saving || !this.#dirty;
    save.type = "submit";
    actions.append(preview, save);
    form.append(add, tags, actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.#save();
    });
    panel.append(heading, help, form);
    return panel;
  }

  #sectionEditor(index: number): HTMLElement {
    const section = this.#content!.sections[index]!;
    const group = document.createElement("fieldset");
    group.className = "article-section-editor";
    const legend = document.createElement("legend");
    legend.textContent = `Section ${index + 1}`;
    const heading = this.#textField("Heading", section.heading, 300);
    heading.input.addEventListener("input", () => {
      section.heading = heading.input.value;
      this.#markDirty();
    });
    const paragraphs = this.#textareaField(
      "Paragraphs",
      section.paragraphs.join("\n\n"),
      20_000,
      8,
    );
    paragraphs.input.addEventListener("input", () => {
      section.paragraphs = paragraphsFromText(paragraphs.input.value);
      this.#markDirty();
    });
    group.append(legend, heading.field, paragraphs.field);
    if (this.#content!.sections.length > 1) {
      const remove = button("Remove section");
      remove.addEventListener("click", () => {
        this.#content!.sections.splice(index, 1);
        this.#markDirty();
        this.#render();
      });
      group.append(remove);
    }
    return group;
  }

  #textField(label: string, value: string, maxLength: number): {
    field: HTMLElement; input: HTMLInputElement;
  } {
    const field = document.createElement("div");
    field.className = "field-group";
    const labelElement = document.createElement("label");
    const input = document.createElement("input");
    input.id = `article-field-${crypto.randomUUID()}`;
    input.value = value;
    input.maxLength = maxLength;
    labelElement.htmlFor = input.id;
    labelElement.textContent = label;
    field.append(labelElement, input);
    return { field, input };
  }

  #textareaField(label: string, value: string, maxLength: number, rows: number): {
    field: HTMLElement; input: HTMLTextAreaElement;
  } {
    const field = document.createElement("div");
    field.className = "field-group";
    const labelElement = document.createElement("label");
    const input = document.createElement("textarea");
    input.id = `article-field-${crypto.randomUUID()}`;
    input.value = value;
    input.maxLength = maxLength;
    input.rows = rows;
    labelElement.htmlFor = input.id;
    labelElement.textContent = label;
    field.append(labelElement, input);
    return { field, input };
  }

  #preview(): HTMLElement {
    const panel = document.createElement("section");
    panel.className = "dashboard-panel article-preview-panel";
    const heading = document.createElement("h2");
    heading.textContent = "Rendered preview";
    panel.append(heading);
    if (this.#previewHtml) {
      const frame = document.createElement("iframe");
      frame.title = "Article preview";
      frame.setAttribute("sandbox", "");
      frame.srcdoc = this.#previewHtml;
      panel.append(frame);
    } else {
      const empty = document.createElement("ui-empty-state");
      empty.textContent = "No rendered preview is available.";
      panel.append(empty);
    }
    return panel;
  }

  #evidencePanel(): HTMLElement {
    const panel = document.createElement("section");
    panel.className = "dashboard-panel article-provenance";
    const heading = document.createElement("h2");
    heading.textContent = `Evidence (${formatInteger(this.#evidence.length)})`;
    panel.append(heading);
    if (this.#evidence.length === 0) {
      const empty = document.createElement("ui-empty-state");
      empty.textContent = "No evidence is attached to this revision.";
      panel.append(empty);
      return panel;
    }
    const list = document.createElement("ol");
    list.className = "article-evidence-list";
    for (const evidence of this.#evidence) {
      const item = document.createElement("li");
      const kind = document.createElement("small");
      kind.textContent = `${evidence.evidence_type === "segment" ? "Segment" : "Original response"} · ${evidence.topic_name}`;
      const quote = document.createElement("blockquote");
      quote.textContent = evidence.text;
      const source = document.createElement("p");
      source.textContent = evidence.question_context
        ? `${evidence.source} · ${evidence.question_context.question_text}`
        : evidence.source;
      item.append(kind, quote, source);
      if (evidence.evidence_type === "segment") {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = "View untouched original";
        const original = document.createElement("p");
        original.textContent = evidence.original_text;
        details.append(summary, original);
        item.append(details);
      }
      list.append(item);
    }
    panel.append(list);
    return panel;
  }

  #historyPanel(): HTMLElement {
    const panel = document.createElement("section");
    panel.className = "dashboard-panel article-history";
    const heading = document.createElement("h2");
    heading.textContent = "History";
    const list = document.createElement("ol");
    for (const event of this.#history) {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = auditLabels[event.action];
      const date = document.createElement("time");
      date.dateTime = event.created_at;
      date.textContent = formatDateTime(event.created_at);
      item.append(title, date);
      if (event.note) {
        const note = document.createElement("p");
        note.textContent = event.note;
        item.append(note);
      }
      list.append(item);
    }
    panel.append(heading, list);
    return panel;
  }

  #validatedDraft(): { content: EditableArticleContent; themeIds: number[]; topics: string[] } {
    const title = this.#title.trim();
    if (!title) throw new Error("Article title is required.");
    const content = this.#content!;
    content.standfirst = content.standfirst.trim();
    content.sections = content.sections.map((section) => ({
      ...section,
      heading: section.heading.trim(),
      paragraphs: section.paragraphs.map((paragraph) => paragraph.trim()).filter(Boolean),
    }));
    if (content.sections.some((section) => !section.heading || section.paragraphs.length === 0)) {
      throw new Error("Every section needs a heading and at least one paragraph.");
    }
    const themeIds = parseThemeIds(this.#themeIds);
    const topics = parseTopicNames(this.#topics);
    if (themeIds.length === 0 && topics.length === 0) {
      throw new Error("Add at least one theme or topic tag.");
    }
    this.#title = title;
    return { content, themeIds, topics };
  }

  async #refreshPreview(): Promise<string | null> {
    if (!this.#article || this.#articleId === null) return null;
    try {
      const draft = this.#validatedDraft();
      this.#saving = true;
      this.#error = null;
      this.#render();
      const preview = await api.previewArticle(this.#articleId, {
        title: this.#title,
        structured_content: draft.content,
        expected_revision_id: this.#article.current_revision.id,
      });
      this.#previewHtml = preview.rendered_html;
      this.#saving = false;
      this.#render();
      this.#announce("Preview refreshed.");
      return preview.rendered_html;
    } catch (error) {
      this.#saving = false;
      this.#conflict = error instanceof ApiError && error.status === 409;
      this.#error = error instanceof ApiError
        ? userFacingError(error)
        : error instanceof Error ? error.message : userFacingError(error);
      this.#render();
      return null;
    }
  }

  async #save(): Promise<boolean> {
    if (!this.#article || this.#articleId === null) return false;
    let draft: {
      content: EditableArticleContent;
      themeIds: number[];
      topics: string[];
    };
    try {
      draft = this.#validatedDraft();
    } catch (error) {
      this.#error = error instanceof Error ? error.message : "Article fields are invalid.";
      this.#render();
      return false;
    }
    this.#saving = true;
    this.#error = null;
    this.#render();
    try {
      const preview = await api.previewArticle(this.#articleId, {
        title: this.#title,
        structured_content: draft.content,
        expected_revision_id: this.#article.current_revision.id,
      });
      await api.updateArticle(this.#articleId, {
        title: this.#title,
        structured_content: draft.content,
        rendered_html: preview.rendered_html,
        theme_ids: draft.themeIds,
        topics: draft.topics.map((name) => ({ name })),
        expected_revision_id: this.#article.current_revision.id,
      });
      this.#invalidateArticleData();
      this.#saving = false;
      this.#dirty = false;
      await this.#load();
      this.#announce("Revision saved.");
      return true;
    } catch (error) {
      this.#saving = false;
      this.#conflict = error instanceof ApiError && error.status === 409;
      this.#error = userFacingError(error);
      this.#render();
      return false;
    }
  }

  async #submitForReview(): Promise<void> {
    if (this.#dirty && !(await this.#save())) return;
    await this.#transition("submit");
  }

  #confirmTransition(
    heading: string,
    description: string,
    confirmLabel: string,
    action: "approve" | "archive",
  ): void {
    const dialog = document.createElement("ui-dialog") as UiDialog;
    dialog.setAttribute("heading", heading);
    const copy = document.createElement("p");
    copy.textContent = description;
    const summary = document.createElement("dl");
    summary.className = "generation-summary";
    const facts: Array<[string, string]> = [
      ["Article", this.#article!.title],
      ["Revision", String(this.#article!.current_revision.revision_number)],
      ["Evidence", formatInteger(this.#article!.evidence_count)],
      ["Tags", String(this.#article!.theme_ids.length + this.#article!.topics.length)],
    ];
    for (const [term, value] of facts) {
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      dd.textContent = value;
      summary.append(dt, dd);
    }
    const actions = document.createElement("div");
    actions.className = "generation-actions";
    const cancel = button("Cancel");
    cancel.addEventListener("click", () => dialog.close());
    const confirm = button(confirmLabel, true);
    confirm.addEventListener("click", () => {
      dialog.close();
      void this.#transition(action);
    });
    actions.append(cancel, confirm);
    dialog.append(copy, summary, actions);
    this.append(dialog);
    dialog.showModal();
  }

  async #transition(
    action: "submit" | "approve" | "return-to-draft" | "archive",
  ): Promise<void> {
    if (this.#articleId === null) return;
    this.#busy = true;
    this.#error = null;
    this.#render();
    try {
      await api.transitionArticle(this.#articleId, action);
      this.#invalidateArticleData();
      await this.#load();
      this.#announce(action === "approve" ? "Article approved."
        : action === "archive" ? "Article archived."
          : action === "submit" ? "Article submitted for review."
            : "Editable draft created.");
    } catch (error) {
      this.#busy = false;
      this.#error = userFacingError(error);
      this.#render();
    }
  }

  #invalidateArticleData(): void {
    queryStore.invalidate("dashboard:");
    queryStore.invalidate("taxonomy:");
    queryStore.invalidate("articles:");
  }

  #markDirty(): void {
    this.#dirty = true;
    this.#previewHtml = null;
    const save = this.querySelector<HTMLButtonElement>('[data-action="save-article"]');
    if (save && !this.#saving) save.disabled = false;
    this.querySelector(".article-preview-panel")?.setAttribute("data-stale", "");
  }

  #announce(message: string): void {
    if (this.#live) this.#live.textContent = message;
  }
}

customElements.define("article-detail-page", ArticleDetailPage);
