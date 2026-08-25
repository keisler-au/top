import { generationHref, primaryNavigation } from "./navigation.js";
import type { RouteMatch } from "./router.js";
import { Router } from "./router.js";

export class DashboardApp extends HTMLElement {
  readonly #router = new Router();
  #menuOpen = false;
  #outlet: HTMLElement | null = null;
  #navigation: HTMLElement | null = null;
  #menuButton: HTMLButtonElement | null = null;
  #routeStatus: HTMLElement | null = null;
  #content: HTMLElement | null = null;

  connectedCallback(): void {
    this.#renderShell();
    this.#router.addEventListener("route-change", this.#handleRouteChange);
    this.#router.start();
    document.addEventListener("keydown", this.#handleKeydown);
  }

  disconnectedCallback(): void {
    this.#router.removeEventListener("route-change", this.#handleRouteChange);
    this.#router.stop();
    document.removeEventListener("keydown", this.#handleKeydown);
  }

  readonly #handleRouteChange = (event: Event): void => {
    const route = (event as CustomEvent<RouteMatch>).detail;
    this.#renderRoute(route);
  };

  readonly #handleKeydown = (event: KeyboardEvent): void => {
    if (event.key === "Escape" && this.#menuOpen) {
      this.#setMenu(false);
      this.#menuButton?.focus();
    }
  };

  #renderShell(): void {
    this.replaceChildren();

    const shell = document.createElement("div");
    shell.className = "app-shell";

    const header = document.createElement("header");
    header.className = "mobile-header";
    const menuButton = document.createElement("button");
    menuButton.className = "icon-button mobile-menu-button";
    menuButton.type = "button";
    menuButton.setAttribute("aria-label", "Open navigation");
    menuButton.setAttribute("aria-controls", "primary-navigation");
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.textContent = "☰";
    menuButton.addEventListener("click", () => this.#setMenu(!this.#menuOpen));
    this.#menuButton = menuButton;
    const compactBrand = document.createElement("a");
    compactBrand.href = "/";
    compactBrand.dataset.route = "";
    compactBrand.className = "compact-brand";
    compactBrand.textContent = "Evidence dashboard";
    const mobileGenerate = document.createElement("a");
    mobileGenerate.href = generationHref;
    mobileGenerate.dataset.route = "";
    mobileGenerate.className = "mobile-create-link";
    mobileGenerate.setAttribute("aria-label", "Generate an article");
    mobileGenerate.textContent = "+";
    header.append(menuButton, compactBrand, mobileGenerate);

    const sidebar = document.createElement("aside");
    sidebar.className = "sidebar";
    sidebar.id = "primary-navigation";
    const brand = document.createElement("a");
    brand.href = "/";
    brand.dataset.route = "";
    brand.className = "brand";
    const brandMark = document.createElement("span");
    brandMark.className = "brand-mark";
    brandMark.setAttribute("aria-hidden", "true");
    brandMark.textContent = "E";
    const brandText = document.createElement("span");
    brandText.textContent = "Evidence dashboard";
    brand.append(brandMark, brandText);

    const nav = document.createElement("nav");
    nav.setAttribute("aria-label", "Primary navigation");
    const list = document.createElement("ul");
    list.className = "navigation-list";
    for (const item of primaryNavigation) {
      const listItem = document.createElement("li");
      const link = document.createElement("a");
      link.href = item.href;
      link.dataset.route = "";
      link.dataset.routeName = item.route;
      link.className = "navigation-link";
      const icon = document.createElement("span");
      icon.className = "navigation-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = item.icon;
      const label = document.createElement("span");
      label.textContent = item.label;
      link.append(icon, label);
      link.addEventListener("click", () => this.#setMenu(false));
      listItem.append(link);
      list.append(listItem);
    }
    nav.append(list);
    this.#navigation = nav;

    const createLink = document.createElement("a");
    createLink.href = generationHref;
    createLink.dataset.route = "";
    createLink.className = "create-link";
    createLink.textContent = "Generate article";
    createLink.addEventListener("click", () => this.#setMenu(false));
    sidebar.append(brand, nav, createLink);

    const backdrop = document.createElement("button");
    backdrop.type = "button";
    backdrop.className = "navigation-backdrop";
    backdrop.setAttribute("aria-label", "Close navigation");
    backdrop.addEventListener("click", () => this.#setMenu(false));

    const content = document.createElement("div");
    content.className = "app-content";
    this.#content = content;
    const routeStatus = document.createElement("p");
    routeStatus.className = "visually-hidden";
    routeStatus.setAttribute("aria-live", "polite");
    routeStatus.setAttribute("aria-atomic", "true");
    this.#routeStatus = routeStatus;
    const main = document.createElement("main");
    main.id = "main-content";
    main.className = "page-content";
    main.tabIndex = -1;
    this.#outlet = main;
    content.append(routeStatus, main);

    shell.append(header, sidebar, backdrop, content);
    this.append(shell);
  }

  #renderRoute(route: RouteMatch): void {
    if (!this.#outlet) {
      return;
    }
    document.title = `${route.title} · Evidence dashboard`;
    const page = route.name === "overview" || route.name === "taxonomy"
      ? document.createElement("dashboard-overview")
      : route.name === "forms"
        ? document.createElement("forms-page")
        : document.createElement("placeholder-page");
    if (route.name === "taxonomy") {
      page.setAttribute("view", "taxonomy");
    } else if (route.name !== "overview" && route.name !== "forms") {
      page.setAttribute("route", route.name);
    }
    this.#outlet.replaceChildren(page);
    for (const link of this.#navigation?.querySelectorAll("a") ?? []) {
      const active = link.dataset.routeName === route.name
        || (route.name === "article" && link.dataset.routeName === "articles");
      link.toggleAttribute("aria-current", active);
    }
    if (this.#routeStatus) {
      this.#routeStatus.textContent = `${route.title} page loaded`;
    }
    this.#setMenu(false);
  }

  #setMenu(open: boolean): void {
    this.#menuOpen = open;
    this.toggleAttribute("menu-open", open);
    this.#menuButton?.setAttribute("aria-expanded", String(open));
    this.#menuButton?.setAttribute(
      "aria-label",
      open ? "Close navigation" : "Open navigation",
    );
    this.#content?.toggleAttribute("inert", open);
    if (open) {
      requestAnimationFrame(() => {
        this.#navigation?.querySelector<HTMLAnchorElement>("a")?.focus();
      });
    }
  }
}

customElements.define("dashboard-app", DashboardApp);
