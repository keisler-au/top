const template = document.createElement("template");
template.innerHTML = `
  <style>
    :host {
      align-items: center;
      background: var(--status-background, var(--color-surface-muted));
      border-radius: 999px;
      color: var(--status-color, var(--color-text-muted));
      display: inline-flex;
      font-size: var(--font-size-sm);
      font-weight: 700;
      gap: var(--space-2);
      line-height: 1;
      min-block-size: 1.75rem;
      padding: 0 var(--space-3);
    }
    :host::before {
      background: currentColor;
      border-radius: 50%;
      content: "";
      inline-size: 0.5rem;
      block-size: 0.5rem;
    }
    :host([tone="positive"]) {
      --status-background: var(--color-positive-soft);
      --status-color: var(--color-positive);
    }
    :host([tone="warning"]) {
      --status-background: var(--color-warning-soft);
      --status-color: var(--color-warning);
    }
    :host([tone="danger"]) {
      --status-background: var(--color-danger-soft);
      --status-color: var(--color-danger);
    }
  </style>
  <slot></slot>
`;

export class UiStatus extends HTMLElement {
  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
  }

}

customElements.define("ui-status", UiStatus);
