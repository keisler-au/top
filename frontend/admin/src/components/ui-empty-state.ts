export class UiEmptyState extends HTMLElement {
  connectedCallback(): void {
    if (!this.hasAttribute("role")) {
      this.setAttribute("role", "status");
    }
  }
}

customElements.define("ui-empty-state", UiEmptyState);
