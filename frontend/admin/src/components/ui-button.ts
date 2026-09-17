const template = document.createElement("template");
template.innerHTML = `
  <style>
    :host { display: inline-flex; }
    button {
      align-items: center;
      background: var(--button-background, var(--color-primary));
      border: 1px solid var(--button-border, transparent);
      border-radius: var(--radius-sm);
      color: var(--button-color, white);
      cursor: pointer;
      display: inline-flex;
      font: inherit;
      font-weight: 700;
      gap: var(--space-2);
      justify-content: center;
      min-block-size: 2.75rem;
      padding: var(--space-2) var(--space-4);
      transition: background-color 140ms ease, border-color 140ms ease;
    }
    button:hover:not(:disabled) { background: var(--color-primary-strong); }
    button:focus-visible {
      outline: 3px solid var(--color-focus);
      outline-offset: 2px;
    }
    button:disabled { cursor: not-allowed; opacity: 0.55; }
    :host([variant="secondary"]) button {
      --button-background: var(--color-surface);
      --button-border: var(--color-border-strong);
      --button-color: var(--color-text);
    }
    :host([variant="secondary"]) button:hover:not(:disabled) {
      background: var(--color-surface-muted);
    }
    :host([variant="quiet"]) button {
      --button-background: transparent;
      --button-color: var(--color-primary-strong);
    }
    :host([variant="quiet"]) button:hover:not(:disabled) {
      background: var(--color-primary-soft);
    }
    @media (prefers-reduced-motion: reduce) {
      button { transition: none; }
    }
  </style>
  <button type="button"><slot></slot></button>
`;

export class UiButton extends HTMLElement {
  static readonly observedAttributes = ["disabled", "type"];
  readonly #button: HTMLButtonElement;

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.append(template.content.cloneNode(true));
    const button = root.querySelector("button");
    if (!(button instanceof HTMLButtonElement)) {
      throw new Error("ui-button template is missing its button");
    }
    this.#button = button;
    this.#button.addEventListener("click", () => {
      if (this.#button.type === "submit" && !this.#button.disabled) {
        this.closest("form")?.requestSubmit();
      }
    });
  }

  connectedCallback(): void {
    this.#synchronize();
  }

  attributeChangedCallback(): void {
    this.#synchronize();
  }

  get disabled(): boolean {
    return this.hasAttribute("disabled");
  }

  set disabled(value: boolean) {
    this.toggleAttribute("disabled", value);
  }

  override focus(options?: FocusOptions): void {
    this.#button.focus(options);
  }

  #synchronize(): void {
    this.#button.disabled = this.disabled;
    this.#button.type = this.getAttribute("type") === "submit" ? "submit" : "button";
  }
}

customElements.define("ui-button", UiButton);
