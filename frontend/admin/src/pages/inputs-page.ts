import type { InputFilters } from "../api/contracts.js";
import { inputFilterError, inputsSearch, inputsState, type InputsState } from "./inputs-state.js";
import { api } from "../app-context.js";
import { userFacingError } from "../api/errors.js";
import { LatestReviewRequest } from "./taxonomy-review-state.js";

function text(tag: string, content: string): HTMLElement {
  const node = document.createElement(tag);
  node.textContent = content;
  return node;
}

export class InputsPage extends HTMLElement {
  readonly #requests = new LatestReviewRequest();
  #state: InputsState = inputsState(new URLSearchParams(window.location.search));
  #controls = new Map<string, HTMLInputElement | HTMLSelectElement>();
  #validation: HTMLElement | null = null;
  #content: HTMLElement | null = null;
  connectedCallback(): void {
    this.#state = inputsState(new URLSearchParams(window.location.search));
    this.#content = document.createElement("section");
    this.#content.setAttribute("aria-live", "polite");
    this.replaceChildren(text("h1", "Inputs"),
      text("p", "Topic and theme associations come from the published run. Empty associations are normal; processing status describes evidence preparation."),
      this.#filterForm(),
      this.#button("Refresh", () => void this.#load()), this.#content);
    void this.#load();
  }
  disconnectedCallback(): void { this.#requests.cancel(); }
  #button(label: string, action: () => void): HTMLButtonElement {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "secondary-button";
    node.textContent = label;
    node.addEventListener("click", action);
    return node;
  }
  #updateUrl(): void {
    const search = inputsSearch(this.#state);
    window.history.replaceState({}, "", `/inputs${search ? "?" + search : ""}`);
  }
  #page(change: number): void {
    this.#state.offset += change;
    this.#updateUrl();
    void this.#load();
  }
  #filterForm(): HTMLElement {
    this.#controls.clear();
    const panel = document.createElement("section");
    panel.className = "dashboard-panel";
    const form = document.createElement("form");
    form.className = "article-filter-form";
    const field = (labelText: string, key: string, type = "text"): HTMLLabelElement => {
      const label = document.createElement("label");
      label.textContent = labelText;
      const input = document.createElement("input");
      input.name = key;
      input.type = type;
      if (type === "number") { input.min = "1"; input.step = "1"; }
      input.value = String(this.#state.filters[key as keyof InputFilters] ?? "");
      this.#controls.set(key, input);
      label.append(input);
      return label;
    };
    const select = (labelText: string, key: string, choices: Array<[string, string]>): HTMLLabelElement => {
      const label = document.createElement("label");
      label.textContent = labelText;
      const input = document.createElement("select");
      input.name = key;
      for (const [value, name] of choices) {
        const option = document.createElement("option"); option.value = value; option.textContent = name; input.append(option);
      }
      input.value = String(this.#state.filters[key as keyof InputFilters] ?? "");
      this.#controls.set(key, input); label.append(input); return label;
    };
    form.append(field("Search answer or question", "search", "search"),
      select("Processing status", "status", [["", "All statuses"], ["new", "New"], ["ineligible", "Excluded from analysis"],
        ["ready_for_embedding", "Awaiting meaning analysis"], ["ready_for_analysis", "Ready for topic analysis"], ["completed", "Prepared"]]),
      select("Published topic association", "has_topic", [["", "Any"], ["true", "Has a topic"], ["false", "Has no topic"]]),
      field("Topic name contains", "topic"), field("Theme name contains", "theme"),
      field("Received from (UTC)", "created_from", "date"), field("Received through (UTC)", "created_to", "date"));
    const more = document.createElement("details");
    more.className = "inputs-filter-attributes";
    const summary = text("summary", "Additional attributes");
    const advanced = document.createElement("div"); advanced.className = "article-filter-form";
    advanced.append(field("Source", "source"), field("Form key", "form_key"), field("Question key", "question_key"),
      field("Question version", "question_version", "number"), field("Submission key", "submission_key"));
    if (["source", "form_key", "question_key", "question_version", "submission_key"].some(key => key in this.#state.filters)) more.open = true;
    more.append(summary, text("p", "Source and Form key must be supplied together. Question and submission keys belong to that form. These attributes match exactly."), advanced);
    const submit = document.createElement("button"); submit.type = "submit"; submit.className = "primary-button"; submit.textContent = "Apply filters";
    form.append(more, submit, this.#button("Clear filters", () => {
      this.#state = { filters: {}, offset: 0 };
      for (const input of this.#controls.values()) input.value = "";
      this.#validation?.replaceChildren(); this.#updateUrl(); void this.#load();
    }));
    this.#validation = document.createElement("section"); this.#validation.setAttribute("aria-live", "polite");
    form.addEventListener("submit", event => {
      event.preventDefault();
      const parameters = new URLSearchParams();
      for (const [key, input] of this.#controls) if (input.value.trim()) parameters.set(key, input.value.trim());
      const next = inputsState(parameters);
      const invalid = inputFilterError(next.filters);
      if (invalid) { this.#validation?.replaceChildren(text("ui-alert", invalid)); return; }
      this.#validation?.replaceChildren(); this.#state = next; this.#updateUrl(); void this.#load();
    });
    panel.append(text("h2", "Filter responses"),
      text("p", "Filters combine. Topic and theme filters use the current published analysis. Has no topic includes responses outside that analysis."), form, this.#validation);
    return panel;
  }
  async #load(): Promise<void> {
    const controller = this.#requests.begin();
    const invalid = inputFilterError(this.#state.filters);
    if (invalid) { this.#content?.replaceChildren(text("ui-alert", invalid)); return; }
    this.#content?.replaceChildren(text("ui-loading", "Loading inputs…"));
    try {
      const items = await api.inputs(this.#state.offset, { signal: controller.signal }, this.#state.filters);
      if (!this.#requests.current(controller)) return;
      this.#content?.replaceChildren(text("p", `${items.length} responses on page ${this.#state.offset / 50 + 1}${Object.keys(this.#state.filters).length ? " · Filters applied" : ""}`));
      if (!items.length) this.#content?.append(text("ui-empty-state", Object.keys(this.#state.filters).length ? "No inputs match these filters on this page. Adjust or clear the filters." : "No inputs on this page."));
      for (const item of items) {
        const card = document.createElement("article");
        card.className = "evidence-card";
        card.append(text("h2", `Input ${item.id}`), text("p", `Question: ${item.question_context.question_text}`),
          text("blockquote", item.original_text), text("p", `Processing: ${item.status}`),
          text("p", `Source: ${item.source} · Form: ${item.question_context.form_key} · Question: ${item.question_context.question_key} · Version: ${item.question_context.question_version}`),
          text("p", `Received: ${item.created_at}${item.submission_key ? " · Submission: " + item.submission_key : ""}`),
          text("p", item.published_taxonomy_run_id === null ? "No published taxonomy yet." : `Published run ${item.published_taxonomy_run_id}`),
          text("p", `Topics: ${item.topics.map((topic) => topic.name).join(', ') || 'None'}`),
          text("p", `Themes: ${item.themes.map((theme) => theme.name).join(', ') || 'None'}`));
        this.#content?.append(card);
      }
      if (this.#state.offset > 0) this.#content?.append(this.#button("Previous", () => { this.#page(-50); }));
      if (items.length === 50 && this.#state.offset < 100000) this.#content?.append(this.#button("Next", () => { this.#page(50); }));
    } catch (error) {
      if (this.#requests.current(controller)) this.#content?.replaceChildren(text("ui-alert", userFacingError(error)),
        this.#button("Try again", () => void this.#load()));
    }
  }
}
customElements.define("inputs-page", InputsPage);
