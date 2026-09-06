import type {
  ArticleTemplate,
  EvidenceItem,
  GenerationJob,
  GenerationStrategy,
  RecommendationItem,
  TaxonomyItem,
  TaxonomyType,
  TemplateVersion,
} from "../api/contracts.js";
import { ApiError, userFacingError } from "../api/errors.js";
import { api } from "../app-context.js";
import type { UiDialog } from "../components/ui-dialog.js";
import { formatInteger } from "../utils/format.js";
import {
  generationJobIsActive,
  generationPollDelay,
  generationSearch,
  generationState,
  type GenerationState,
  type GenerationStep,
} from "./generation-state.js";
import {
  templateDraft,
  restoredTemplateSelection,
  templateValidationResult,
  type TemplateDraft,
  type TemplateField,
  type TemplateSelection,
} from "./template-admin-state.js";

const stepOrder: readonly GenerationStep[] = [
  "strategy",
  "target",
  "evidence",
  "template",
  "guidance",
  "confirm",
  "progress",
];

const stepLabels: Readonly<Record<GenerationStep, string>> = {
  strategy: "Strategy",
  target: "Target",
  evidence: "Evidence",
  template: "Template",
  guidance: "Guidance",
  confirm: "Confirm",
  progress: "Progress",
};

function button(label: string, primary = false): HTMLButtonElement {
  const element = document.createElement("button");
  element.type = "button";
  element.className = primary ? "primary-button" : "secondary-button";
  element.textContent = label;
  return element;
}

function navigate(url: string): void {
  window.history.pushState({}, "", url);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export class GenerationPage extends HTMLElement {
  #state: GenerationState = generationState(new URLSearchParams());
  #target: TaxonomyItem | null = null;
  #targets: Array<TaxonomyItem | RecommendationItem> = [];
  #evidence: EvidenceItem[] = [];
  #evidenceTotal = 0;
  #selectedEvidence = new Set<string>();
  #templates: ArticleTemplate[] = [];
  #selectedTemplateId: number | null = null;
  #selectedVersionId: number | null = null;
  #previewHtml: string | null = null;
  #guidance = "";
  #job: GenerationJob | null = null;
  #content: HTMLElement | null = null;
  #liveRegion: HTMLElement | null = null;
  #controller: AbortController | null = null;
  #pollTimer: number | null = null;
  #pollCount = 0;
  #busy = false;
  #error: string | null = null;
  #targetSearch = "";
  #managingTemplates = false;
  #templateAdminMode: "create" | "version" | null = null;
  #managedTemplateId: number | null = null;
  #templateDraft: TemplateDraft | null = null;
  #templateFieldErrors: Partial<Record<TemplateField, string>> = {};
  #templateSelectionBeforeManagement: TemplateSelection | null = null;

  connectedCallback(): void {
    this.#state = generationState(new URLSearchParams(window.location.search));
    document.addEventListener("visibilitychange", this.#handleVisibilityChange);
    this.#renderShell();
    void this.#initialize();
  }

  disconnectedCallback(): void {
    document.removeEventListener("visibilitychange", this.#handleVisibilityChange);
    this.#controller?.abort();
    this.#clearPollTimer();
  }

  readonly #handleVisibilityChange = (): void => {
    if (
      document.visibilityState === "visible"
      && this.#state.jobId !== null
      && (this.#job === null || generationJobIsActive(this.#job.status))
    ) {
      this.#schedulePoll(0);
    }
  };

  async #initialize(): Promise<void> {
    if (this.#state.jobId !== null) {
      await this.#pollJob(true);
      return;
    }
    if (this.#state.key !== null) {
      await this.#restoreTargetFromUrl();
      if (
        this.#state.key !== null
        && ["template", "guidance", "confirm"].includes(this.#state.step)
      ) {
        await this.#loadTemplates();
      }
      return;
    }
    this.#renderStep();
  }

  #renderShell(): void {
    this.replaceChildren();
    const header = document.createElement("header");
    header.className = "generation-page-heading";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "Create";
    const heading = document.createElement("h1");
    heading.tabIndex = -1;
    heading.textContent = "Generate an article";
    const description = document.createElement("p");
    description.className = "page-description";
    description.textContent =
      "Choose a well-supported target, inspect its evidence, and create a draft for human review.";
    header.append(eyebrow, heading, description);

    const progress = document.createElement("nav");
    progress.className = "generation-progress";
    progress.setAttribute("aria-label", "Article generation steps");
    const list = document.createElement("ol");
    const currentIndex = stepOrder.indexOf(this.#state.step);
    for (const [index, step] of stepOrder.entries()) {
      const item = document.createElement("li");
      item.textContent = stepLabels[step];
      if (index === currentIndex) item.setAttribute("aria-current", "step");
      if (index < currentIndex) item.dataset.complete = "";
      list.append(item);
    }
    progress.append(list);

    const content = document.createElement("section");
    content.className = "dashboard-panel generation-panel";
    this.#content = content;
    const live = document.createElement("p");
    live.className = "visually-hidden";
    live.setAttribute("aria-live", "polite");
    live.setAttribute("aria-atomic", "true");
    this.#liveRegion = live;
    this.append(header, progress, content, live);
    requestAnimationFrame(() => heading.focus());
  }

  #renderStep(): void {
    if (!this.#content) return;
    this.#content.replaceChildren();
    if (this.#busy) {
      const loading = document.createElement("ui-loading");
      loading.textContent = this.#state.step === "progress"
        ? "Checking generation progress…"
        : "Loading generation options…";
      this.#content.append(loading);
      return;
    }
    if (this.#error) this.#content.append(this.#alert(this.#error));
    switch (this.#state.step) {
      case "strategy": this.#renderStrategy(); break;
      case "target": this.#renderTarget(); break;
      case "evidence": this.#renderEvidence(); break;
      case "template": this.#renderTemplate(); break;
      case "guidance": this.#renderGuidance(); break;
      case "confirm": this.#renderConfirm(); break;
      case "progress": this.#renderProgress(); break;
    }
  }

  #alert(message: string, tone = "danger"): HTMLElement {
    const alert = document.createElement("ui-alert");
    alert.setAttribute("tone", tone);
    alert.setAttribute("role", "alert");
    alert.textContent = message;
    return alert;
  }

  #stepHeading(title: string, description: string): HTMLElement {
    const group = document.createElement("div");
    group.className = "generation-step-heading";
    const heading = document.createElement("h2");
    heading.tabIndex = -1;
    heading.textContent = title;
    const copy = document.createElement("p");
    copy.textContent = description;
    group.append(heading, copy);
    requestAnimationFrame(() => heading.focus());
    return group;
  }

  #renderStrategy(): void {
    if (!this.#content) return;
    const form = document.createElement("form");
    form.className = "generation-form";
    const strategy = document.createElement("fieldset");
    const strategyLegend = document.createElement("legend");
    strategyLegend.textContent = "How should the target be chosen?";
    strategy.append(strategyLegend);
    const choices: Array<[GenerationStrategy, string, string]> = [
      ["specific", "Choose a specific target", "Search all themes or topics."],
      ["most-evidence", "Most evidence", "Start with the strongest evidence base."],
      ["least-covered", "Least covered", "Prioritize evidence without approved coverage."],
    ];
    for (const [value, label, description] of choices) {
      strategy.append(this.#radioCard("generation-strategy", value, label, description,
        value === this.#state.strategy));
    }

    const taxonomy = document.createElement("fieldset");
    const taxonomyLegend = document.createElement("legend");
    taxonomyLegend.textContent = "Use themes or topics?";
    taxonomy.append(taxonomyLegend);
    taxonomy.append(
      this.#radioCard("generation-type", "theme", "Themes", "Broad patterns across related topics.",
        this.#state.type === "theme"),
      this.#radioCard("generation-type", "topic", "Topics", "Specific, question-aware classifications.",
        this.#state.type === "topic"),
    );
    const actions = document.createElement("div");
    actions.className = "generation-actions";
    const next = button("Choose a target", true);
    next.type = "submit";
    actions.append(next);
    form.append(
      this.#stepHeading("Choose a strategy", "Recommendations use current evidence and approved article coverage."),
      strategy,
      taxonomy,
      actions,
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(form);
      this.#state.strategy = data.get("generation-strategy") as GenerationStrategy;
      this.#state.type = data.get("generation-type") as TaxonomyType;
      this.#state.key = null;
      this.#target = null;
      this.#targets = [];
      this.#setStep("target");
      void this.#loadTargets();
    });
    this.#content.append(form);
  }

  #radioCard(
    name: string,
    value: string,
    label: string,
    description: string,
    checked: boolean,
  ): HTMLLabelElement {
    const card = document.createElement("label");
    card.className = "choice-card";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = name;
    input.value = value;
    input.checked = checked;
    const copy = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = label;
    const detail = document.createElement("small");
    detail.textContent = description;
    copy.append(title, detail);
    card.append(input, copy);
    return card;
  }

  async #loadTargets(search = ""): Promise<void> {
    this.#startRequest();
    this.#targetSearch = search;
    try {
      if (this.#state.strategy === "specific") {
        const response = await api.taxonomy({
          type: this.#state.type,
          search: search || undefined,
          sort: "evidence",
          direction: "desc",
          page: 1,
          pageSize: 100,
        }, { signal: this.#controller?.signal });
        this.#targets = response.items.filter((item) => item.generation_eligible);
      } else {
        const response = await api.recommendations(
          this.#state.type,
          this.#state.strategy,
          20,
          { signal: this.#controller?.signal },
        );
        this.#targets = response.items;
      }
      this.#finishRequest();
    } catch (error) {
      if (!this.#controller?.signal.aborted) this.#failRequest(error);
    }
  }

  #renderTarget(): void {
    if (!this.#content) return;
    const wrapper = document.createElement("div");
    wrapper.className = "generation-form";
    wrapper.append(this.#stepHeading(
      "Choose a target",
      this.#state.strategy === "specific"
        ? "Select a target with attributable evidence."
        : "Recommendations are recalculated from the current coverage data.",
    ));
    if (this.#state.strategy === "specific") {
      const search = document.createElement("form");
      search.className = "generation-search";
      const label = document.createElement("label");
      label.htmlFor = "generation-target-search";
      label.textContent = `Search ${this.#state.type === "theme" ? "themes" : "topics"}`;
      const row = document.createElement("div");
      const input = document.createElement("input");
      input.id = "generation-target-search";
      input.type = "search";
      input.value = this.#targetSearch;
      const submit = button("Search");
      submit.type = "submit";
      row.append(input, submit);
      search.append(label, row);
      search.addEventListener("submit", (event) => {
        event.preventDefault();
        void this.#loadTargets(input.value.trim());
      });
      wrapper.append(search);
    }
    if (this.#targets.length === 0) {
      const empty = document.createElement("ui-empty-state");
      empty.textContent = "No generation-eligible targets were found.";
      wrapper.append(empty);
    } else {
      const list = document.createElement("ul");
      list.className = "generation-target-list";
      for (const item of this.#targets) list.append(this.#targetItem(item));
      wrapper.append(list);
    }
    const actions = this.#actions("Back", () => this.#setStep("strategy"));
    wrapper.append(actions);
    this.#content.append(wrapper);
  }

  #targetItem(item: TaxonomyItem | RecommendationItem): HTMLLIElement {
    const row = document.createElement("li");
    const copy = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = item.name;
    const description = document.createElement("p");
    description.textContent = "explanation" in item
      ? item.explanation
      : item.description || "No description available.";
    const counts = document.createElement("small");
    counts.textContent = `${formatInteger(item.evidence_count)} evidence items · ${formatInteger(item.approved_article_count)} approved articles`;
    copy.append(heading, description, counts);
    const choose = button("Use this target", true);
    choose.addEventListener("click", () => void this.#chooseTarget(item));
    row.append(copy, choose);
    return row;
  }

  async #chooseTarget(item: TaxonomyItem | RecommendationItem): Promise<void> {
    this.#target = item;
    this.#state.key = String(item.key);
    this.#setStep("evidence", false);
    await this.#loadEvidence();
  }

  async #restoreTargetFromUrl(): Promise<void> {
    const key = this.#state.key;
    if (key === null) return;
    this.#startRequest();
    try {
      const target = await api.taxonomyDetail(
        this.#state.type,
        key,
        { signal: this.#controller?.signal },
      );
      if (!target.generation_eligible) {
        this.#state.key = null;
        this.#state.step = "target";
        this.#target = null;
        this.#busy = false;
        await this.#loadTargets();
        this.#error = "This target no longer has evidence and cannot be used for generation.";
        this.#renderStep();
        return;
      }
      this.#target = target;
      await this.#loadEvidence(false);
    } catch (error) {
      if (!this.#controller?.signal.aborted) {
        const message = userFacingError(error);
        this.#state.key = null;
        this.#state.step = "target";
        this.#targets = [];
        this.#busy = false;
        await this.#loadTargets();
        this.#error = message;
        this.#renderStep();
      }
    }
  }

  async #loadEvidence(startRequest = true): Promise<void> {
    if (!this.#target) return;
    if (startRequest) this.#startRequest();
    try {
      const response = await api.evidence(
        this.#target.type,
        this.#target.key,
        1,
        100,
        { signal: this.#controller?.signal },
      );
      this.#evidence = response.items;
      this.#evidenceTotal = response.total;
      this.#selectedEvidence = new Set(response.items.map((item) => item.id));
      this.#finishRequest();
    } catch (error) {
      if (!this.#controller?.signal.aborted) this.#failRequest(error);
    }
  }

  #renderEvidence(): void {
    if (!this.#content) return;
    const wrapper = document.createElement("div");
    wrapper.className = "generation-form";
    wrapper.append(this.#stepHeading(
      "Inspect the evidence",
      `Choose the source points to freeze for ${this.#target?.name ?? "this target"}.`,
    ));
    if (this.#evidenceTotal > 100) {
      wrapper.append(this.#alert(
        `The backend will use at most the newest 100 of ${formatInteger(this.#evidenceTotal)} evidence items.`,
        "warning",
      ));
    }
    const controls = document.createElement("div");
    controls.className = "evidence-selection-controls";
    const count = document.createElement("strong");
    count.textContent = `${formatInteger(this.#selectedEvidence.size)} selected`;
    const all = button("Select all");
    all.addEventListener("click", () => {
      this.#selectedEvidence = new Set(this.#evidence.map((item) => item.id));
      this.#renderStep();
    });
    const none = button("Clear selection");
    none.addEventListener("click", () => {
      this.#selectedEvidence.clear();
      this.#renderStep();
    });
    controls.append(count, all, none);
    wrapper.append(controls);
    const list = document.createElement("ul");
    list.className = "generation-evidence-list";
    for (const item of this.#evidence) list.append(this.#evidenceItem(item));
    wrapper.append(list);
    const next = button("Choose a template", true);
    next.disabled = this.#selectedEvidence.size === 0;
    next.addEventListener("click", () => {
      this.#setStep("template", false);
      void this.#loadTemplates();
    });
    wrapper.append(this.#actions("Back to targets", () => {
      this.#setStep("target");
      void this.#loadTargets(this.#targetSearch);
    }, next));
    this.#content.append(wrapper);
  }

  #evidenceItem(item: EvidenceItem): HTMLLIElement {
    const row = document.createElement("li");
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = this.#selectedEvidence.has(item.id);
    input.addEventListener("change", () => {
      if (input.checked) this.#selectedEvidence.add(item.id);
      else this.#selectedEvidence.delete(item.id);
      this.#renderStep();
    });
    const copy = document.createElement("span");
    const kind = document.createElement("small");
    kind.textContent = item.type === "segment" ? "System-created segment" : "Source response";
    const quote = document.createElement("q");
    quote.textContent = item.excerpt;
    const context = document.createElement("small");
    context.textContent = item.question_context
      ? `${item.source} · ${item.question_context.question_text}`
      : item.source;
    copy.append(kind, quote, context);
    label.append(input, copy);
    row.append(label);
    return row;
  }

  async #loadTemplates(): Promise<void> {
    this.#startRequest();
    try {
      this.#templates = await api.articleTemplates({ signal: this.#controller?.signal });
      const firstActive = this.#templates.find((template) => template.status === "active");
      if (this.#selectedTemplateId === null && firstActive) {
        this.#selectTemplate(firstActive, false);
      }
      this.#finishRequest();
      if (this.#selectedTemplateId !== null && this.#selectedVersionId !== null) {
        await this.#loadPreview();
      }
    } catch (error) {
      if (!this.#controller?.signal.aborted) this.#failRequest(error);
    }
  }

  #selectTemplate(template: ArticleTemplate, rerender = true): void {
    this.#selectedTemplateId = template.id;
    this.#selectedVersionId = template.versions[0]?.id ?? null;
    this.#previewHtml = null;
    if (rerender) {
      this.#renderStep();
      if (this.#selectedVersionId !== null) void this.#loadPreview();
    }
  }

  async #loadPreview(): Promise<void> {
    if (this.#selectedTemplateId === null || this.#selectedVersionId === null) return;
    const templateId = this.#selectedTemplateId;
    const versionId = this.#selectedVersionId;
    try {
      const preview = await api.previewArticleTemplate(templateId, {
        version_id: versionId,
        title: this.#target?.name ?? "Example article",
        standfirst: "A preview of the selected evidence-grounded article template.",
        sections: [{
          heading: "Evidence overview",
          paragraphs: ["Generated article sections will be rendered safely in this structure."],
        }],
      }, { signal: this.#controller?.signal });
      if (templateId === this.#selectedTemplateId && versionId === this.#selectedVersionId) {
        this.#previewHtml = preview.rendered_html;
        this.#error = null;
        this.#renderStep();
      }
    } catch (error) {
      if (!this.#controller?.signal.aborted) {
        this.#error = userFacingError(error);
        this.#renderStep();
      }
    }
  }

  #renderTemplate(): void {
    if (!this.#content) return;
    if (this.#managingTemplates) {
      this.#renderTemplateManagement();
      return;
    }
    const wrapper = document.createElement("div");
    wrapper.className = "generation-form";
    wrapper.append(this.#stepHeading(
      "Choose a template",
      "The selected immutable version will be frozen with the generation job.",
    ));
    const manage = button("Manage templates");
    manage.addEventListener("click", () => {
      this.#templateSelectionBeforeManagement = this.#currentTemplateSelection();
      this.#managingTemplates = true;
      this.#templateAdminMode = null;
      this.#renderStep();
    });
    wrapper.append(manage);
    const activeTemplates = this.#templates.filter((template) => template.status === "active");
    if (activeTemplates.length === 0) {
      const empty = document.createElement("ui-empty-state");
      empty.textContent = "No active article templates are available.";
      wrapper.append(empty);
    } else {
      const layout = document.createElement("div");
      layout.className = "template-selection-layout";
      const choices = document.createElement("fieldset");
      const legend = document.createElement("legend");
      legend.textContent = "Active templates";
      choices.append(legend);
      for (const template of activeTemplates) {
        const label = this.#radioCard(
          "article-template",
          String(template.id),
          template.name,
          template.description ?? "No description available.",
          template.id === this.#selectedTemplateId,
        );
        label.querySelector("input")?.addEventListener("change", () => this.#selectTemplate(template));
        choices.append(label);
      }
      const selectedTemplate = this.#selectedTemplate();
      if (selectedTemplate && selectedTemplate.versions.length > 0) {
        const versionField = document.createElement("div");
        versionField.className = "field-group";
        const versionLabel = document.createElement("label");
        versionLabel.htmlFor = "article-template-version";
        versionLabel.textContent = "Template version";
        const versionSelect = document.createElement("select");
        versionSelect.id = "article-template-version";
        for (const version of selectedTemplate.versions) {
          const option = document.createElement("option");
          option.value = String(version.id);
          option.textContent = `Version ${version.version}`;
          versionSelect.append(option);
        }
        versionSelect.value = String(this.#selectedVersionId);
        versionSelect.addEventListener("change", () => {
          this.#selectedVersionId = Number.parseInt(versionSelect.value, 10);
          this.#previewHtml = null;
          this.#renderStep();
          void this.#loadPreview();
        });
        versionField.append(versionLabel, versionSelect);
        choices.append(versionField);
      }
      const preview = document.createElement("div");
      preview.className = "template-preview";
      const previewHeading = document.createElement("h3");
      previewHeading.textContent = "Safe preview";
      preview.append(previewHeading);
      if (this.#previewHtml) {
        const frame = document.createElement("iframe");
        frame.title = "Selected article template preview";
        frame.setAttribute("sandbox", "");
        frame.srcdoc = this.#previewHtml;
        preview.append(frame);
      } else {
        const loading = document.createElement("ui-loading");
        loading.textContent = "Rendering preview…";
        preview.append(loading);
      }
      layout.append(choices, preview);
      wrapper.append(layout);
    }
    const next = button("Add guidance", true);
    next.disabled = this.#selectedVersionId === null || this.#previewHtml === null;
    next.addEventListener("click", () => this.#setStep("guidance"));
    wrapper.append(this.#actions("Back to evidence", () => this.#setStep("evidence"), next));
    this.#content.append(wrapper);
  }

  #renderTemplateManagement(): void {
    if (!this.#content) return;
    const wrapper = document.createElement("div");
    wrapper.className = "generation-form template-management";
    wrapper.append(this.#stepHeading(
      "Manage article templates",
      "Create immutable template versions without losing this generation request.",
    ));
    const back = button("← Back to template selection");
    back.addEventListener("click", () => {
      const restored = restoredTemplateSelection(
        this.#templates,
        this.#templateSelectionBeforeManagement,
        this.#currentTemplateSelection(),
      );
      this.#selectedTemplateId = restored?.templateId ?? null;
      this.#selectedVersionId = restored?.versionId ?? null;
      this.#previewHtml = null;
      this.#templateSelectionBeforeManagement = null;
      this.#managingTemplates = false;
      this.#templateAdminMode = null;
      this.#templateDraft = null;
      this.#templateFieldErrors = {};
      this.#renderStep();
      if (this.#selectedVersionId !== null) void this.#loadPreview();
    });
    wrapper.append(back, this.#placeholderReference());

    if (this.#templateAdminMode === "create") {
      wrapper.append(this.#templateEditorForm());
    } else if (this.#templateAdminMode === "version") {
      const template = this.#templates.find(
        (item) => item.id === this.#managedTemplateId,
      );
      if (template) wrapper.append(this.#templateEditorForm(template));
    } else {
      const create = button("Create template", true);
      create.addEventListener("click", () => {
        this.#templateAdminMode = "create";
        this.#templateDraft = templateDraft();
        this.#templateFieldErrors = {};
        this.#renderStep();
      });
      wrapper.append(create, this.#templateAdminList());
    }

    if (this.#previewHtml && this.#selectedVersionId !== null) {
      const preview = document.createElement("section");
      preview.className = "template-preview template-admin-preview";
      const heading = document.createElement("h3");
      heading.textContent = "Server-rendered preview";
      const frame = document.createElement("iframe");
      frame.title = "Managed template preview";
      frame.setAttribute("sandbox", "");
      frame.srcdoc = this.#previewHtml;
      preview.append(heading, frame);
      wrapper.append(preview);
    }
    this.#content.append(wrapper);
  }

  #placeholderReference(): HTMLElement {
    const details = document.createElement("details");
    details.className = "template-placeholder-reference";
    const summary = document.createElement("summary");
    summary.textContent = "Allowed placeholder reference";
    const copy = document.createElement("p");
    copy.textContent = "Templates must contain {{title}} and {{article_body}} exactly once. {{standfirst}} and {{published_at}} are optional. Scripts, event handlers, forms, embeds, remote assets, and unsafe links are rejected by the server.";
    details.append(summary, copy);
    return details;
  }

  #templateAdminList(): HTMLElement {
    const list = document.createElement("ul");
    list.className = "template-admin-list";
    for (const template of this.#templates) {
      const item = document.createElement("li");
      const header = document.createElement("div");
      const heading = document.createElement("h3");
      heading.textContent = template.name;
      const state = document.createElement("ui-status");
      state.setAttribute("tone", template.status === "active" ? "positive" : "neutral");
      state.textContent = template.status === "active" ? "Active" : "Archived";
      header.append(heading, state);
      const description = document.createElement("p");
      description.textContent = template.description ?? "No description provided.";
      const versions = document.createElement("ol");
      versions.className = "template-version-list";
      for (const version of template.versions) {
        const versionItem = document.createElement("li");
        const versionHeader = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = `Version ${version.version}`;
        const usage = document.createElement("span");
        usage.textContent = `${formatInteger(version.used_by_article_count)} article${version.used_by_article_count === 1 ? "" : "s"}`;
        versionHeader.append(title, usage);
        const placeholders = document.createElement("small");
        placeholders.textContent = `Placeholders: ${version.allowed_placeholders.join(", ")}`;
        const source = document.createElement("details");
        const sourceSummary = document.createElement("summary");
        sourceSummary.textContent = "Inspect HTML source";
        const code = document.createElement("code");
        code.textContent = version.html_source;
        source.append(sourceSummary, code);
        const preview = button("Preview");
        preview.addEventListener("click", () => {
          this.#selectedTemplateId = template.id;
          this.#selectedVersionId = version.id;
          this.#previewHtml = null;
          void this.#loadPreview();
        });
        versionItem.append(versionHeader, placeholders, source, preview);
        versions.append(versionItem);
      }
      const actions = document.createElement("div");
      actions.className = "row-actions";
      if (template.status === "active") {
        const addVersion = button("Add version");
        addVersion.addEventListener("click", () => {
          this.#managedTemplateId = template.id;
          this.#templateAdminMode = "version";
          this.#templateDraft = templateDraft(template);
          this.#templateFieldErrors = {};
          this.#renderStep();
        });
        const archive = button("Archive");
        archive.addEventListener("click", () => this.#confirmArchiveTemplate(template));
        actions.append(addVersion, archive);
      }
      item.append(header, description, versions, actions);
      list.append(item);
    }
    return list;
  }

  #templateEditorForm(template?: ArticleTemplate): HTMLElement {
    const form = document.createElement("form");
    form.className = "template-admin-form";
    const draft = this.#templateDraft ?? templateDraft(template);
    this.#templateDraft = draft;
    const heading = document.createElement("h3");
    heading.textContent = template
      ? `Add a version to ${template.name}`
      : "Create an article template";
    form.append(heading);

    let nameInput: HTMLInputElement | null = null;
    let descriptionInput: HTMLTextAreaElement | null = null;
    if (!template) {
      const name = this.#templateTextField("Template name", 120, "name", draft.name);
      nameInput = name.input;
      nameInput.required = true;
      const description = this.#templateTextareaField(
        "Description (optional)", 2000, 3, "description", draft.description,
      );
      descriptionInput = description.input;
      form.append(name.field, description.field);
    }
    const source = this.#templateTextareaField(
      "Template HTML", 100_000, 18, "html_source", draft.htmlSource,
    );
    source.input.required = true;
    source.input.spellcheck = false;
    const creator = this.#templateTextField(
      "Created by (optional)", 200, "created_by", draft.createdBy,
    );
    const actions = document.createElement("div");
    actions.className = "generation-actions";
    const cancel = button("Cancel");
    cancel.addEventListener("click", () => {
      this.#templateAdminMode = null;
      this.#templateDraft = null;
      this.#templateFieldErrors = {};
      this.#renderStep();
    });
    const submit = button(template ? "Create version" : "Create template", true);
    submit.type = "submit";
    actions.append(cancel, submit);
    form.append(source.field, creator.field, actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.#saveTemplate(
        template,
        nameInput?.value.trim() ?? "",
        descriptionInput?.value.trim() || null,
        source.input.value,
        creator.input.value.trim() || null,
      );
    });
    return form;
  }

  #templateTextField(
    labelText: string,
    maxLength: number,
    fieldName: TemplateField,
    value: string,
  ): {
    field: HTMLElement; input: HTMLInputElement;
  } {
    const field = document.createElement("div");
    field.className = "field-group";
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.id = `template-field-${crypto.randomUUID()}`;
    input.maxLength = maxLength;
    input.value = value;
    input.addEventListener("input", () => this.#updateTemplateDraft(fieldName, input.value));
    label.htmlFor = input.id;
    label.textContent = labelText;
    field.append(label, input);
    this.#appendTemplateFieldError(field, input, fieldName);
    return { field, input };
  }

  #templateTextareaField(
    labelText: string,
    maxLength: number,
    rows: number,
    fieldName: TemplateField,
    value: string,
  ): {
    field: HTMLElement; input: HTMLTextAreaElement;
  } {
    const field = document.createElement("div");
    field.className = "field-group";
    const label = document.createElement("label");
    const input = document.createElement("textarea");
    input.id = `template-field-${crypto.randomUUID()}`;
    input.maxLength = maxLength;
    input.rows = rows;
    input.value = value;
    input.addEventListener("input", () => this.#updateTemplateDraft(fieldName, input.value));
    label.htmlFor = input.id;
    label.textContent = labelText;
    field.append(label, input);
    this.#appendTemplateFieldError(field, input, fieldName);
    return { field, input };
  }

  #updateTemplateDraft(fieldName: TemplateField, value: string): void {
    if (!this.#templateDraft) return;
    if (fieldName === "html_source") this.#templateDraft.htmlSource = value;
    else if (fieldName === "created_by") this.#templateDraft.createdBy = value;
    else this.#templateDraft[fieldName] = value;
    delete this.#templateFieldErrors[fieldName];
  }

  #appendTemplateFieldError(
    field: HTMLElement,
    input: HTMLInputElement | HTMLTextAreaElement,
    fieldName: TemplateField,
  ): void {
    const message = this.#templateFieldErrors[fieldName];
    if (!message) return;
    const error = document.createElement("small");
    error.className = "field-error";
    error.id = `${input.id}-error`;
    error.textContent = message;
    input.setAttribute("aria-invalid", "true");
    input.setAttribute("aria-describedby", error.id);
    field.append(error);
  }

  async #saveTemplate(
    template: ArticleTemplate | undefined,
    name: string,
    description: string | null,
    htmlSource: string,
    createdBy: string | null,
  ): Promise<void> {
    this.#templateFieldErrors = {};
    this.#startRequest();
    try {
      const saved = template
        ? await api.createArticleTemplateVersion(template.id, {
          html_source: htmlSource,
          created_by: createdBy,
        }, { signal: this.#controller?.signal })
        : await api.createArticleTemplate({
          name,
          description,
          html_source: htmlSource,
          created_by: createdBy,
        }, { signal: this.#controller?.signal });
      const existing = this.#templates.findIndex((item) => item.id === saved.id);
      if (existing >= 0) this.#templates[existing] = saved;
      else this.#templates.push(saved);
      this.#templates.sort((left, right) => left.name.localeCompare(right.name));
      this.#selectedTemplateId = saved.id;
      this.#selectedVersionId = saved.versions[0]?.id ?? null;
      this.#managedTemplateId = saved.id;
      this.#templateAdminMode = null;
      this.#templateDraft = null;
      this.#templateFieldErrors = {};
      this.#finishRequest();
      this.#announce(template ? "Template version created." : "Template created.");
      if (this.#selectedVersionId !== null) await this.#loadPreview();
    } catch (error) {
      if (!this.#controller?.signal.aborted) {
        const validation = templateValidationResult(error, template === undefined);
        this.#templateFieldErrors = validation.fields;
        this.#finishRequest(validation.summary);
      }
    }
  }

  #confirmArchiveTemplate(template: ArticleTemplate): void {
    const dialog = document.createElement("ui-dialog") as UiDialog;
    dialog.setAttribute("heading", `Archive ${template.name}?`);
    const copy = document.createElement("p");
    copy.textContent = "Existing articles keep their immutable template version, but this template cannot be selected for new generation jobs.";
    const actions = document.createElement("div");
    actions.className = "generation-actions";
    const cancel = button("Cancel");
    cancel.addEventListener("click", () => dialog.close());
    const archive = button("Archive template", true);
    archive.addEventListener("click", () => {
      dialog.close();
      void this.#archiveTemplate(template.id);
    });
    actions.append(cancel, archive);
    dialog.append(copy, actions);
    this.append(dialog);
    dialog.showModal();
  }

  async #archiveTemplate(templateId: number): Promise<void> {
    this.#startRequest();
    try {
      const archived = await api.archiveArticleTemplate(templateId, {
        signal: this.#controller?.signal,
      });
      const index = this.#templates.findIndex((item) => item.id === templateId);
      if (index >= 0) this.#templates[index] = archived;
      if (this.#selectedTemplateId === templateId) {
        const replacement = this.#templates.find((item) => item.status === "active");
        this.#selectedTemplateId = replacement?.id ?? null;
        this.#selectedVersionId = replacement?.versions[0]?.id ?? null;
        this.#previewHtml = null;
      }
      this.#finishRequest();
      this.#announce("Template archived.");
      if (this.#selectedVersionId !== null) await this.#loadPreview();
    } catch (error) {
      if (!this.#controller?.signal.aborted) this.#failRequest(error);
    }
  }

  #renderGuidance(): void {
    if (!this.#content) return;
    const form = document.createElement("form");
    form.className = "generation-form";
    const field = document.createElement("div");
    field.className = "field-group";
    const label = document.createElement("label");
    label.htmlFor = "editorial-guidance";
    label.textContent = "Editorial guidance (optional)";
    const input = document.createElement("textarea");
    input.id = "editorial-guidance";
    input.maxLength = 4000;
    input.rows = 8;
    input.value = this.#guidance;
    input.placeholder = "For example: emphasize practical next steps and use a concise tone.";
    const help = document.createElement("small");
    help.textContent = "Up to 4,000 characters. Evidence and taxonomy constraints still apply.";
    field.append(label, input, help);
    const next = button("Review request", true);
    next.type = "submit";
    form.append(
      this.#stepHeading("Add editorial guidance", "Shape the draft without changing its frozen evidence scope."),
      field,
      this.#actions("Back to template", () => this.#setStep("template"), next),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      this.#guidance = input.value.trim();
      this.#setStep("confirm");
    });
    this.#content.append(form);
  }

  #renderConfirm(): void {
    if (!this.#content) return;
    const wrapper = document.createElement("div");
    wrapper.className = "generation-form";
    wrapper.append(this.#stepHeading(
      "Confirm generation request",
      "Generation creates a draft ready for review. It never approves an article.",
    ));
    const summary = document.createElement("dl");
    summary.className = "generation-summary";
    const template = this.#selectedTemplate();
    const version = template?.versions.find((item) => item.id === this.#selectedVersionId);
    this.#summaryFact(summary, "Strategy", this.#strategyLabel());
    this.#summaryFact(summary, "Target", this.#target?.name ?? "Not selected");
    this.#summaryFact(summary, "Evidence", `${formatInteger(this.#selectedEvidence.size)} source points`);
    this.#summaryFact(summary, "Template", template && version
      ? `${template.name}, version ${version.version}`
      : "Not selected");
    this.#summaryFact(summary, "Guidance", this.#guidance || "No additional guidance");
    wrapper.append(summary);
    const submit = button("Generate article", true);
    submit.addEventListener("click", () => void this.#submitJob());
    wrapper.append(this.#actions("Back to guidance", () => this.#setStep("guidance"), submit));
    this.#content.append(wrapper);
  }

  #summaryFact(list: HTMLDListElement, term: string, value: string): void {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    list.append(dt, dd);
  }

  #strategyLabel(): string {
    if (this.#state.strategy === "most-evidence") return "Most evidence";
    if (this.#state.strategy === "least-covered") return "Least covered";
    return "Specific target";
  }

  #selectedTemplate(): ArticleTemplate | undefined {
    return this.#templates.find((template) => template.id === this.#selectedTemplateId);
  }

  #currentTemplateSelection(): TemplateSelection | null {
    return this.#selectedTemplateId !== null && this.#selectedVersionId !== null
      ? { templateId: this.#selectedTemplateId, versionId: this.#selectedVersionId }
      : null;
  }

  async #submitJob(): Promise<void> {
    if (!this.#target || this.#selectedVersionId === null) return;
    this.#startRequest();
    try {
      const job = await api.createGenerationJob({
        strategy: this.#state.strategy,
        taxonomy_type: this.#target.type,
        taxonomy_key: String(this.#target.key),
        template_version_id: this.#selectedVersionId,
        editorial_guidance: this.#guidance || null,
        evidence_ids: [...this.#selectedEvidence],
      }, { signal: this.#controller?.signal });
      this.#job = job;
      this.#state.jobId = job.id;
      this.#state.step = "progress";
      this.#pollCount = 0;
      this.#finishRequest();
      this.#replaceUrl();
      this.#announce("Article generation queued.");
      this.#schedulePoll();
    } catch (error) {
      if (!this.#controller?.signal.aborted) this.#failRequest(error);
    }
  }

  async #pollJob(initial = false): Promise<void> {
    const jobId = this.#state.jobId;
    if (jobId === null) return;
    this.#clearPollTimer();
    if (initial) this.#startRequest();
    else {
      this.#controller?.abort();
      this.#controller = new AbortController();
    }
    const controller = this.#controller ?? new AbortController();
    this.#controller = controller;
    try {
      const previousStatus = this.#job?.status;
      const job = await api.generationJob(jobId, { signal: controller.signal });
      this.#job = job;
      this.#state.strategy = job.strategy;
      this.#state.type = job.taxonomy_type;
      this.#state.key = job.taxonomy_key;
      this.#busy = false;
      this.#error = null;
      this.#renderStep();
      if (previousStatus !== job.status) this.#announce(this.#jobStatus(job));
      if (generationJobIsActive(job.status)) {
        this.#pollCount += 1;
        this.#schedulePoll();
      } else if (job.status === "completed" && job.resulting_article_id !== null) {
        window.setTimeout(() => {
          if (this.isConnected) navigate(`/articles/${job.resulting_article_id}`);
        }, 600);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        this.#busy = false;
        this.#error = userFacingError(error);
        this.#renderStep();
        if (
          !(error instanceof ApiError)
          || error.status === 408
          || error.status === 429
          || error.status >= 500
        ) {
          this.#pollCount += 1;
          this.#schedulePoll();
        }
      }
    }
  }

  #schedulePoll(delay?: number): void {
    this.#clearPollTimer();
    this.#pollTimer = window.setTimeout(
      () => void this.#pollJob(),
      delay ?? generationPollDelay(
        this.#pollCount,
        document.visibilityState === "visible",
      ),
    );
  }

  #clearPollTimer(): void {
    if (this.#pollTimer !== null) {
      window.clearTimeout(this.#pollTimer);
      this.#pollTimer = null;
    }
  }

  #renderProgress(): void {
    if (!this.#content) return;
    const wrapper = document.createElement("div");
    wrapper.className = "generation-form generation-job";
    wrapper.append(this.#stepHeading(
      "Generation progress",
      "This job is durable. You can bookmark or refresh this URL without losing it.",
    ));
    if (!this.#job) {
      const retry = button("Check again", true);
      retry.addEventListener("click", () => void this.#pollJob(true));
      wrapper.append(retry);
      this.#content.append(wrapper);
      return;
    }
    const status = document.createElement("ui-status");
    status.setAttribute("tone", this.#job.status === "failed" ? "danger"
      : this.#job.status === "completed" ? "positive" : "neutral");
    status.textContent = this.#jobStatus(this.#job);
    const facts = document.createElement("dl");
    facts.className = "generation-summary";
    this.#summaryFact(facts, "Target", this.#job.taxonomy_name);
    this.#summaryFact(facts, "Job", `#${this.#job.id}`);
    this.#summaryFact(facts, "Attempts", String(this.#job.attempts));
    wrapper.append(status, facts);
    if (this.#job.last_error) wrapper.append(this.#alert(this.#job.last_error));
    const actions = document.createElement("div");
    actions.className = "generation-actions";
    if (this.#job.status === "failed" || this.#job.status === "dismissed") {
      const retry = button("Retry generation", true);
      retry.addEventListener("click", () => void this.#retryJob());
      actions.append(retry);
      const restart = button("Edit a new request");
      restart.addEventListener("click", () => void this.#restartFromJob());
      actions.append(restart);
    } else if (this.#job.status === "pending") {
      const check = button("Check now", true);
      check.addEventListener("click", () => void this.#pollJob());
      actions.append(check);
      const dismiss = button("Dismiss job");
      dismiss.addEventListener("click", () => void this.#dismissJob());
      actions.append(dismiss);
    } else if (this.#job.status === "processing") {
      const check = button("Check now", true);
      check.addEventListener("click", () => void this.#pollJob());
      actions.append(check);
    } else if (this.#job.status === "completed" && this.#job.resulting_article_id !== null) {
      const link = document.createElement("a");
      link.href = `/articles/${this.#job.resulting_article_id}`;
      link.dataset.route = "";
      link.className = "primary-link";
      link.textContent = "Open article review";
      actions.append(link);
    }
    wrapper.append(actions);
    this.#content.append(wrapper);
  }

  #jobStatus(job: GenerationJob): string {
    switch (job.status) {
      case "pending": return "Waiting to generate";
      case "processing": return "Generating the article";
      case "completed": return "Draft ready for review";
      case "failed": return "Generation failed";
      case "dismissed": return "Generation dismissed";
    }
  }

  async #retryJob(): Promise<void> {
    if (!this.#job) return;
    this.#startRequest();
    try {
      this.#job = await api.retryGenerationJob(this.#job.id, {
        signal: this.#controller?.signal,
      });
      this.#pollCount = 0;
      this.#finishRequest();
      this.#announce("Generation queued for retry.");
      this.#schedulePoll();
    } catch (error) {
      if (!this.#controller?.signal.aborted) this.#failRequest(error);
    }
  }

  async #dismissJob(): Promise<void> {
    if (!this.#job) return;
    this.#startRequest();
    try {
      this.#job = await api.dismissGenerationJob(this.#job.id, {
        signal: this.#controller?.signal,
      });
      this.#finishRequest();
      this.#announce("Generation dismissed.");
    } catch (error) {
      if (!this.#controller?.signal.aborted) this.#failRequest(error);
    }
  }

  async #restartFromJob(): Promise<void> {
    const job = this.#job;
    if (!job) return;
    this.#state = {
      step: "evidence",
      strategy: job.strategy,
      type: job.taxonomy_type,
      key: job.taxonomy_key,
      sourceStrategy: null,
      jobId: null,
    };
    this.#job = null;
    this.#replaceUrl();
    await this.#restoreTargetFromUrl();
  }

  #actions(
    backLabel: string,
    backAction: () => void,
    primary?: HTMLElement,
  ): HTMLElement {
    const actions = document.createElement("div");
    actions.className = "generation-actions";
    const back = button(backLabel);
    back.addEventListener("click", backAction);
    actions.append(back);
    if (primary) actions.append(primary);
    return actions;
  }

  #setStep(step: GenerationStep, render = true): void {
    this.#state.step = step;
    this.#state.jobId = step === "progress" ? this.#state.jobId : null;
    this.#error = null;
    this.#replaceUrl();
    this.#renderShell();
    if (render) this.#renderStep();
  }

  #replaceUrl(): void {
    window.history.replaceState({}, "", `/generate?${generationSearch(this.#state)}`);
  }

  #startRequest(): void {
    this.#controller?.abort();
    this.#controller = new AbortController();
    this.#busy = true;
    this.#error = null;
    this.#renderStep();
  }

  #finishRequest(error?: string): void {
    this.#busy = false;
    this.#error = error ?? null;
    this.#renderStep();
  }

  #failRequest(error: unknown): void {
    this.#busy = false;
    this.#error = userFacingError(error);
    this.#renderStep();
  }

  #announce(message: string): void {
    if (this.#liveRegion) this.#liveRegion.textContent = message;
  }
}

customElements.define("generation-page", GenerationPage);
