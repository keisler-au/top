import type { TaxonomyRunReview, TaxonomyRunTopicReview } from "../api/contracts.js";
import { userFacingError } from "../api/errors.js";
import { api } from "../app-context.js";
import { LatestReviewRequest, reviewRunId } from "./taxonomy-review-state.js";

function text(tag: string, value: string): HTMLElement {
  const element = document.createElement(tag);
  element.textContent = value;
  return element;
}
function button(label: string, action: () => void): HTMLButtonElement {
  const element = document.createElement("button");
  element.type = "button";
  element.className = "secondary-button";
  element.textContent = label;
  element.addEventListener("click", action);
  return element;
}

export class TaxonomyReviewPage extends HTMLElement {
  readonly #requests = new LatestReviewRequest();
  #selector: HTMLSelectElement | null = null;
  #content: HTMLElement | null = null;
  #run = reviewRunId(new URLSearchParams(window.location.search));

  connectedCallback(): void {
    const heading = text("h1", "Taxonomy review");
    const help = text("p", "Inspect accepted topics and unresolved clusters. Review does not change a run.");
    const runLabel = document.createElement("label");
    runLabel.textContent = "Run";
    const selector = document.createElement("select");
    this.#selector = selector;
    selector.addEventListener("change", () => {
      this.#run = Number(selector.value);
      const search = new URLSearchParams({ run: selector.value });
      window.history.replaceState({}, "", `/taxonomy-review?${search}`);
      void this.#loadRun();
    });
    runLabel.append(selector);
    const content = document.createElement("section");
    content.setAttribute("aria-live", "polite");
    this.#content = content;
    this.replaceChildren(heading, help, runLabel,
      button("Refresh", () => void this.#loadRuns()), content);
    void this.#loadRuns();
  }

  disconnectedCallback(): void {
    this.#requests.cancel();
  }

  #loading(label: string): void {
    const loading = document.createElement("ui-loading");
    loading.setAttribute("label", label);
    this.#content?.replaceChildren(loading);
  }
  #error(error: unknown, retry: () => void): void {
    const alert = text("ui-alert", userFacingError(error));
    alert.setAttribute("tone", "danger");
    this.#content?.replaceChildren(alert, button("Try again", retry));
  }

  async #loadRuns(): Promise<void> {
    const controller = this.#requests.begin();
    this.#selector?.replaceChildren();
    this.#loading("Loading runs…");
    try {
      const runs = await api.taxonomyRuns({ signal: controller.signal });
      if (!this.#requests.current(controller)) return;
      if (!runs.length) {
        this.#content?.replaceChildren(text("ui-empty-state", "No taxonomy runs yet."));
        return;
      }
      for (const run of runs) {
        const option = document.createElement("option");
        option.value = String(run.id);
        option.textContent = `Run ${run.id} · ${run.status}`;
        this.#selector?.append(option);
      }
      // A deep link may refer to an older run outside the bounded recent list.
      this.#run ??= runs[0]?.id ?? null;
      if (this.#run && !runs.some((run) => run.id === this.#run)) {
        const option = document.createElement("option");
        option.value = String(this.#run);
        option.textContent = `Run ${this.#run}`;
        this.#selector?.append(option);
      }
      if (this.#selector) this.#selector.value = String(this.#run);
      await this.#loadRun();
    } catch (error) {
      if (this.#requests.current(controller)) this.#error(error, () => void this.#loadRuns());
    }
  }

  async #loadRun(): Promise<void> {
    const controller = this.#requests.begin();
    if (!this.#run) return;
    this.#loading("Loading review…");
    try {
      const run = await api.taxonomyRun(this.#run, { signal: controller.signal });
      if (this.#requests.current(controller)) this.#renderRun(run, controller);
    } catch (error) {
      if (this.#requests.current(controller)) this.#error(error, () => void this.#loadRun());
    }
  }

  #renderRun(run: TaxonomyRunReview, owner: AbortController): void {
    const coverage = run.evidence_count === 0 ? "No evidence; no"
      : run.evidence_without_topic_count > 0 ? "Partial" : "Full";
    const gate = run.gate_passed === null ? "Publication checks pending"
      : run.gate_passed ? "Publication checks passed" : "Publication checks failed";
    this.#content?.replaceChildren(
      text("h2", `Run ${run.id} · ${run.status}`),
      text("p", `${coverage} topic coverage · ${run.evidence_count} total evidence · ${run.evidence_with_topic_count} with topics · ${run.evidence_without_topic_count} without topics`),
      text("p", `${run.topic_count} canonical topics · ${run.theme_count} optional themes · ${run.noise_count} unclustered evidence`),
      text("p", `${gate}${run.publication_failures.length ? ': ' + run.publication_failures.join(', ') : ''}`),
      text("h3", "Accepted canonical topics"),
    );
    if (!run.topics.length) this.#content?.append(text("ui-empty-state", "No canonical topics yet."));
    for (const topic of run.topics) this.#content?.append(this.#topic(run.id, topic, owner));
    this.#content?.append(text("h3", "Cluster outcomes"),
      text("p", "Unresolved clusters have no accepted topic. Their evidence is retained; a rejected label does not make the answers invalid."));
    if (!run.clusters.length) this.#content?.append(text("p", "No cluster outcomes yet."));
    for (const cluster of run.clusters) {
      this.#content?.append(text("p", `Cluster ${cluster.id} · question ${cluster.question_id ?? 'unknown'} · ${cluster.support_count} evidence · ${cluster.outcome}${cluster.provisional_name ? ': ' + cluster.provisional_name : ''}${cluster.reasons.length ? ' · Reasons: ' + cluster.reasons.join(', ') : ''}`));
    }
    if (run.truncated) this.#content?.append(text("ui-alert", "Showing the first 100 topics and clusters. This review is limited; totals cover the whole run."));
  }

  #topic(run: number, topic: TaxonomyRunTopicReview, owner: AbortController): HTMLElement {
    const card = document.createElement("article");
    card.className = "evidence-card";
    card.append(text("h4", topic.name), text("p", topic.description),
      text("p", `${topic.support_count} supporting evidence · identity ${topic.topic_id} · ${topic.continuity_decision}`));
    const provenance = document.createElement("details");
    provenance.append(text("summary", "Provisional topics and merge provenance"));
    if (!topic.antecedents.length) provenance.append(text("p", "Historical run: no provisional antecedents recorded."));
    for (const item of topic.antecedents) provenance.append(text("p",
      `${item.name} · provisional ${item.id} · question ${item.question_id ?? 'unknown'} · ${item.support_count} evidence · ${item.relationship} · decision ${item.reconciliation_decision_id}: ${item.description}`));
    const evidence = document.createElement("section");
    let offset = 0;
    const requests = new LatestReviewRequest();
    owner.signal.addEventListener("abort", () => requests.cancel(), { once: true });
    const load = async (): Promise<void> => {
      if (!this.#requests.current(owner)) return;
      const controller = requests.begin();
      const requestedOffset = offset;
      evidence.replaceChildren(text("ui-loading", "Loading evidence…"));
      try {
        const page = await api.taxonomyTopicEvidence(run, topic.id, requestedOffset,
          { signal: controller.signal });
        if (!this.#requests.current(owner) || !requests.current(controller)) return;
        evidence.replaceChildren(text("p", `Evidence from offset ${page.offset}`));
        if (!page.items.length) evidence.append(text("p", "No more evidence."));
        for (const item of page.items) evidence.append(text("blockquote",
          `Evidence ${item.id} · original ${item.original_input_id}${item.segment_input_id ? ' · segment ' + item.segment_input_id : ''}: ${item.text}`));
        if (offset > 0) evidence.append(button("Previous evidence", () => { offset -= page.page_size; void load(); }));
        if (page.items.length === page.page_size && offset + page.page_size <= 100000)
          evidence.append(button("Next evidence", () => { offset += page.page_size; void load(); }));
      } catch (error) {
        if (this.#requests.current(owner) && requests.current(controller)) evidence.replaceChildren(text("ui-alert", userFacingError(error)), button("Retry evidence", () => void load()));
      }
    };
    card.append(provenance, button("View canonical evidence", () => { offset = 0; void load(); }), evidence);
    return card;
  }
}
customElements.define("taxonomy-review-page", TaxonomyReviewPage);
