import type { FormSource } from "../api/contracts.js";
import { userFacingError } from "../api/errors.js";
import { api, queryStore } from "../app-context.js";
import { formatDateTime } from "../utils/format.js";
import {
  createPayload,
  updatePayload,
  type FormSourceFields,
} from "./form-source-state.js";

export class FormsPage extends HTMLElement {
  #form: HTMLFormElement | null = null;
  #formHeading: HTMLHeadingElement | null = null;
  #formMessage: HTMLElement | null = null;
  #listContent: HTMLElement | null = null;
  #submitButton: HTMLButtonElement | null = null;
  #cancelButton: HTMLButtonElement | null = null;
  #editingId: number | null = null;
  #loadController: AbortController | null = null;
  #refreshTimer: number | null = null;

  connectedCallback(): void {
    this.#renderShell();
    void this.#loadSources();
    this.#refreshTimer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        queryStore.invalidate("form-sources:list");
        void this.#loadSources(false);
      }
    }, 5_000);
  }

  disconnectedCallback(): void {
    this.#loadController?.abort();
    if (this.#refreshTimer !== null) {
      window.clearInterval(this.#refreshTimer);
      this.#refreshTimer = null;
    }
  }

  #renderShell(): void {
    this.replaceChildren();
    const header = document.createElement("header");
    header.className = "page-heading forms-page-heading";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "Sources";
    const heading = document.createElement("h1");
    heading.tabIndex = -1;
    heading.textContent = "Forms";
    const description = document.createElement("p");
    description.className = "page-description";
    description.textContent = "Register Google Sheets response tabs for the poller to scan.";
    header.append(eyebrow, heading, description);

    const layout = document.createElement("div");
    layout.className = "forms-layout";
    layout.append(this.#registrationPanel(), this.#sourcesPanel());
    this.append(header, layout);
    requestAnimationFrame(() => heading.focus());
  }

  #registrationPanel(): HTMLElement {
    const panel = document.createElement("section");
    panel.className = "dashboard-panel form-registration-panel";
    const heading = document.createElement("h2");
    heading.textContent = "Register a spreadsheet";
    this.#formHeading = heading;
    const intro = document.createElement("p");
    intro.className = "muted-copy";
    intro.textContent = "The response tab must be append-only and have one header row.";

    const message = document.createElement("div");
    message.className = "form-message";
    message.setAttribute("aria-live", "polite");
    this.#formMessage = message;

    const form = document.createElement("form");
    form.className = "source-form";
    form.noValidate = false;
    this.#form = form;
    form.append(
      this.#field(
        "form-id",
        "Stable form ID",
        "form_id",
        "customer-feedback",
        "Used as the permanent form identity. It cannot be renamed later.",
      ),
      this.#field(
        "spreadsheet-id",
        "Spreadsheet ID or Google Sheets URL",
        "spreadsheet",
        "https://docs.google.com/spreadsheets/d/…/edit",
        "Paste the full URL or only the value between /d/ and /edit.",
      ),
      this.#field(
        "sheet-name",
        "Response tab name",
        "sheet_name",
        "Form Responses 1",
        "This must exactly match the tab containing response rows.",
        "Form Responses 1",
      ),
      this.#field(
        "ignored-headers",
        "Ignored columns",
        "ignored_headers",
        "Timestamp, Email Address",
        "Comma-separated header names. Empty response cells are always skipped.",
        "Timestamp",
        false,
      ),
      this.#numberField(),
      this.#enabledField(),
    );

    const actions = document.createElement("div");
    actions.className = "form-actions";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "primary-link";
    submit.textContent = "Register spreadsheet";
    this.#submitButton = submit;
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "secondary-button";
    cancel.textContent = "Cancel editing";
    cancel.hidden = true;
    cancel.addEventListener("click", () => this.#resetForm());
    this.#cancelButton = cancel;
    actions.append(submit, cancel);
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.#submit();
    });
    panel.append(heading, intro, message, form);
    return panel;
  }

  #field(
    id: string,
    labelText: string,
    name: string,
    placeholder: string,
    helpText: string,
    value = "",
    required = true,
  ): HTMLElement {
    const group = document.createElement("div");
    group.className = "field-group";
    const label = document.createElement("label");
    label.htmlFor = id;
    label.textContent = labelText;
    const input = document.createElement("input");
    input.id = id;
    input.name = name;
    input.type = "text";
    input.placeholder = placeholder;
    input.value = value;
    input.required = required;
    input.setAttribute("aria-describedby", `${id}-help`);
    const help = document.createElement("small");
    help.id = `${id}-help`;
    help.textContent = helpText;
    group.append(label, input, help);
    return group;
  }

  #numberField(): HTMLElement {
    const group = document.createElement("div");
    group.className = "field-group";
    const label = document.createElement("label");
    label.htmlFor = "poll-interval";
    label.textContent = "Polling interval in seconds";
    const input = document.createElement("input");
    input.id = "poll-interval";
    input.name = "poll_interval";
    input.type = "number";
    input.required = true;
    input.min = "1";
    input.max = "86400";
    input.step = "1";
    input.value = "60";
    input.inputMode = "numeric";
    input.setAttribute("aria-describedby", "poll-interval-help");
    const help = document.createElement("small");
    help.id = "poll-interval-help";
    help.textContent = "How often this source becomes eligible for polling.";
    group.append(label, input, help);
    return group;
  }

  #enabledField(): HTMLElement {
    const group = document.createElement("label");
    group.className = "checkbox-field";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = "enabled";
    input.checked = true;
    const copy = document.createElement("span");
    const label = document.createElement("strong");
    label.textContent = "Start polling when registered";
    const help = document.createElement("small");
    help.textContent = "You can pause and resume this source later.";
    copy.append(label, help);
    group.append(input, copy);
    return group;
  }

  #sourcesPanel(): HTMLElement {
    const panel = document.createElement("section");
    panel.className = "dashboard-panel form-sources-panel";
    panel.setAttribute("aria-labelledby", "registered-forms-heading");
    const header = document.createElement("div");
    header.className = "panel-heading-row";
    const copy = document.createElement("div");
    const heading = document.createElement("h2");
    heading.id = "registered-forms-heading";
    heading.textContent = "Registered spreadsheets";
    const description = document.createElement("p");
    description.textContent = "Poller cursor and health for each response tab.";
    copy.append(heading, description);
    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.className = "secondary-button";
    refresh.textContent = "Refresh";
    refresh.addEventListener("click", () => {
      queryStore.invalidate("form-sources");
      void this.#loadSources();
    });
    header.append(copy, refresh);
    const content = document.createElement("div");
    content.className = "form-source-list-content";
    content.setAttribute("aria-live", "polite");
    this.#listContent = content;
    this.#renderLoading();
    panel.append(header, content);
    return panel;
  }

  #formFields(): FormSourceFields {
    if (!this.#form) throw new Error("registration form is unavailable");
    return {
      formId: this.#input("form_id").value,
      spreadsheet: this.#input("spreadsheet").value,
      sheetName: this.#input("sheet_name").value,
      ignoredHeaders: this.#input("ignored_headers").value,
      pollInterval: this.#input("poll_interval").value,
      enabled: this.#input("enabled").checked,
    };
  }

  #input(name: string): HTMLInputElement {
    const input = this.#form?.elements.namedItem(name);
    if (!(input instanceof HTMLInputElement)) {
      throw new Error(`form field ${name} is unavailable`);
    }
    return input;
  }

  async #submit(): Promise<void> {
    if (!this.#form || !this.#submitButton) return;
    if (!this.#form.reportValidity()) return;
    this.#formMessage?.replaceChildren();
    try {
      const fields = this.#formFields();
      this.#setFormBusy(true);
      if (this.#editingId === null) {
        const created = await api.createFormSource(createPayload(fields));
        this.#showFormMessage(
          `Registered ${created.form_id}. It is ready for the poller.`,
          "positive",
        );
        this.#resetForm(false);
      } else {
        const updated = await api.updateFormSource(
          this.#editingId,
          updatePayload(fields),
        );
        this.#showFormMessage(`Saved ${updated.form_id}.`, "positive");
        this.#resetForm(false);
      }
      queryStore.invalidate("form-sources");
      await this.#loadSources();
    } catch (error) {
      const message = error instanceof Error && !(error.name === "ApiError")
        ? error.message
        : userFacingError(error);
      this.#showFormMessage(message, "danger");
    } finally {
      this.#setFormBusy(false);
    }
  }

  #showFormMessage(message: string, tone: "positive" | "danger"): void {
    if (!this.#formMessage) return;
    const alert = document.createElement("ui-alert");
    alert.setAttribute("tone", tone);
    alert.textContent = message;
    this.#formMessage.replaceChildren(alert);
  }

  #setFormBusy(busy: boolean): void {
    if (!this.#form || !this.#submitButton) return;
    this.#form.setAttribute("aria-busy", String(busy));
    for (const element of this.#form.elements) {
      if (
        element instanceof HTMLInputElement
        || element instanceof HTMLButtonElement
      ) {
        element.disabled = busy || (
          (element.name === "form_id" || element.name === "enabled")
          && this.#editingId !== null
        );
      }
    }
    this.#submitButton.textContent = busy
      ? "Saving…"
      : this.#editingId === null
        ? "Register spreadsheet"
        : "Save changes";
  }

  #resetForm(clearMessage = true): void {
    this.#editingId = null;
    this.#form?.reset();
    this.#input("sheet_name").value = "Form Responses 1";
    this.#input("ignored_headers").value = "Timestamp";
    this.#input("poll_interval").value = "60";
    this.#input("form_id").disabled = false;
    this.#input("enabled").disabled = false;
    this.#input("enabled").checked = true;
    this.#formHeading!.textContent = "Register a spreadsheet";
    this.#submitButton!.textContent = "Register spreadsheet";
    if (this.#cancelButton) this.#cancelButton.hidden = true;
    if (clearMessage) this.#formMessage?.replaceChildren();
  }

  #startEdit(source: FormSource): void {
    this.#editingId = source.id;
    this.#input("form_id").value = source.form_id;
    this.#input("form_id").disabled = true;
    this.#input("spreadsheet").value = source.spreadsheet_id;
    this.#input("sheet_name").value = source.sheet_name;
    this.#input("ignored_headers").value = source.ignored_headers.join(", ");
    this.#input("poll_interval").value = String(source.poll_interval_seconds);
    this.#input("enabled").checked = source.enabled;
    this.#input("enabled").disabled = true;
    this.#formHeading!.textContent = `Edit ${source.form_id}`;
    this.#submitButton!.textContent = "Save changes";
    if (this.#cancelButton) this.#cancelButton.hidden = false;
    this.#formMessage?.replaceChildren();
    this.#formHeading?.scrollIntoView({ block: "start" });
    this.#input("spreadsheet").focus();
  }

  async #loadSources(showLoading = true): Promise<void> {
    if (!this.#listContent) return;
    this.#loadController?.abort();
    const controller = new AbortController();
    this.#loadController = controller;
    if (showLoading) this.#renderLoading();
    try {
      const response = await queryStore.fetch(
        "form-sources:list",
        () => api.formSources(1, 100, { signal: controller.signal }),
      );
      if (!controller.signal.aborted) {
        this.#renderSources(response.items, response.total);
      }
    } catch (error) {
      if (!controller.signal.aborted && showLoading) {
        this.#renderListError(error);
      }
    }
  }

  #renderLoading(): void {
    if (!this.#listContent) return;
    const loading = document.createElement("ui-loading");
    loading.setAttribute("label", "Loading registered spreadsheets…");
    this.#listContent.replaceChildren(loading);
  }

  #renderListError(error: unknown): void {
    if (!this.#listContent) return;
    const alert = document.createElement("ui-alert");
    alert.setAttribute("tone", "danger");
    alert.textContent = userFacingError(error);
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "secondary-button";
    retry.textContent = "Try again";
    retry.addEventListener("click", () => void this.#loadSources());
    this.#listContent.replaceChildren(alert, retry);
  }

  #renderSources(sources: FormSource[], total: number): void {
    if (!this.#listContent) return;
    this.#listContent.replaceChildren();
    if (sources.length === 0) {
      const empty = document.createElement("ui-empty-state");
      const heading = document.createElement("h3");
      heading.textContent = "No spreadsheets registered";
      const text = document.createElement("p");
      text.textContent = "Use the registration form to add the first response tab.";
      empty.append(heading, text);
      this.#listContent.append(empty);
      return;
    }
    const summary = document.createElement("p");
    summary.className = "result-summary";
    summary.textContent = `${total} registered spreadsheet${total === 1 ? "" : "s"}`;
    const list = document.createElement("ul");
    list.className = "form-source-list";
    for (const source of sources) {
      const item = document.createElement("li");
      item.append(this.#sourceCard(source));
      list.append(item);
    }
    this.#listContent.append(summary, list);
    if (total > sources.length) {
      const note = document.createElement("p");
      note.className = "muted-copy";
      note.textContent = "Only the first 100 registrations are shown.";
      this.#listContent.append(note);
    }
  }

  #sourceCard(source: FormSource): HTMLElement {
    const article = document.createElement("article");
    article.className = "form-source-card";
    const header = document.createElement("header");
    const titleGroup = document.createElement("div");
    const title = document.createElement("h3");
    title.textContent = source.form_id;
    const tab = document.createElement("p");
    tab.textContent = source.sheet_name;
    titleGroup.append(title, tab);
    const status = document.createElement("ui-status");
    status.textContent = source.enabled ? "Source enabled" : "Paused";
    status.setAttribute("tone", source.enabled ? "positive" : "warning");
    header.append(titleGroup, status);

    const spreadsheet = document.createElement("p");
    spreadsheet.className = "spreadsheet-id";
    spreadsheet.textContent = source.spreadsheet_id;
    spreadsheet.title = source.spreadsheet_id;

    const facts = document.createElement("dl");
    facts.className = "source-facts";
    this.#fact(facts, "Last poll", source.last_polled_at
      ? formatDateTime(source.last_polled_at)
      : "Never");
    this.#fact(facts, "Last read row", String(source.last_read_row));
    this.#fact(facts, "Interval", `${source.poll_interval_seconds} seconds`);
    this.#fact(facts, "Next poll", source.enabled
      ? formatDateTime(source.next_poll_at)
      : "Paused");
    article.append(header, spreadsheet, facts);

    if (source.last_error) {
      const error = document.createElement("ui-alert");
      error.setAttribute("tone", "danger");
      const errorLabel = document.createElement("strong");
      errorLabel.textContent = "Last polling error";
      const errorText = document.createElement("p");
      errorText.textContent = source.last_error;
      error.append(errorLabel, errorText);
      article.append(error);
    }

    const actions = document.createElement("div");
    actions.className = "form-source-actions";
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "secondary-button";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => this.#startEdit(source));
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "quiet-button";
    toggle.textContent = source.enabled ? "Pause polling" : "Resume polling";
    toggle.addEventListener("click", () => {
      void this.#toggleSource(source, toggle);
    });
    actions.append(edit, toggle);
    article.append(actions);
    return article;
  }

  #fact(list: HTMLDListElement, label: string, value: string): void {
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    list.append(term, detail);
  }

  async #toggleSource(
    source: FormSource,
    button: HTMLButtonElement,
  ): Promise<void> {
    button.disabled = true;
    button.textContent = source.enabled ? "Pausing…" : "Resuming…";
    try {
      await api.setFormSourceEnabled(source.id, !source.enabled);
      queryStore.invalidate("form-sources");
      await this.#loadSources();
    } catch (error) {
      button.disabled = false;
      button.textContent = source.enabled ? "Pause polling" : "Resume polling";
      const alert = document.createElement("ui-alert");
      alert.setAttribute("tone", "danger");
      alert.textContent = userFacingError(error);
      button.closest("article")?.prepend(alert);
    }
  }
}

customElements.define("forms-page", FormsPage);
