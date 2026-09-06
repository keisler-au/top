export class UiDialog extends HTMLElement {
  static readonly observedAttributes = ["heading"];
  readonly #dialog: HTMLDialogElement;
  readonly #title: HTMLHeadingElement;
  readonly #body: HTMLDivElement;
  #initialized = false;
  #returnFocus: HTMLElement | null = null;

  constructor() {
    super();
    this.#dialog = document.createElement("dialog");
    this.#dialog.className = "dialog-surface";
    this.#title = document.createElement("h2");
    this.#title.id = `dialog-title-${crypto.randomUUID()}`;
    this.#body = document.createElement("div");
    this.#body.className = "dialog-body";
  }

  connectedCallback(): void {
    if (this.#initialized) {
      return;
    }
    this.#initialized = true;
    this.#title.textContent = this.getAttribute("heading") ?? "Dialog";
    this.#dialog.setAttribute("aria-labelledby", this.#title.id);
    const close = document.createElement("button");
    close.className = "icon-button dialog-close";
    close.type = "button";
    close.setAttribute("aria-label", "Close dialog");
    close.textContent = "×";
    close.addEventListener("click", () => this.close());
    const header = document.createElement("header");
    header.className = "dialog-header";
    header.append(this.#title, close);
    while (this.firstChild) {
      this.#body.append(this.firstChild);
    }
    this.#dialog.append(header, this.#body);
    this.#dialog.addEventListener("click", (event) => {
      if (event.target === this.#dialog) {
        this.close();
      }
    });
    this.#dialog.addEventListener("close", () => {
      if (this.#returnFocus?.isConnected) this.#returnFocus.focus();
      this.#returnFocus = null;
    });
    this.append(this.#dialog);
  }

  attributeChangedCallback(name: string): void {
    if (name === "heading" && this.#initialized) {
      this.#title.textContent = this.getAttribute("heading") ?? "Dialog";
    }
  }

  showModal(): void {
    if (!this.#dialog.open) {
      this.#returnFocus = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      this.#dialog.showModal();
    }
  }

  close(returnValue = ""): void {
    if (this.#dialog.open) {
      this.#dialog.close(returnValue);
    }
  }
}

customElements.define("ui-dialog", UiDialog);
