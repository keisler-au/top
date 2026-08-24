export class UiLoading extends HTMLElement {
  connectedCallback(): void {
    this.setAttribute("role", "status");
    this.setAttribute("aria-live", "polite");
    if (this.childElementCount === 0) {
      const spinner = document.createElement("span");
      spinner.className = "loading-spinner";
      spinner.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.textContent = this.getAttribute("label") ?? "Loading…";
      this.append(spinner, label);
    }
  }
}

customElements.define("ui-loading", UiLoading);
