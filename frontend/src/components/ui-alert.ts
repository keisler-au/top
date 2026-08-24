export class UiAlert extends HTMLElement {
  connectedCallback(): void {
    this.setAttribute("role", this.getAttribute("tone") === "danger" ? "alert" : "status");
    if (!this.hasAttribute("aria-live")) {
      this.setAttribute("aria-live", "polite");
    }
  }
}

customElements.define("ui-alert", UiAlert);
