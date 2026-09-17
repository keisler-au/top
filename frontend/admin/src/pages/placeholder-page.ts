import type { RouteName } from "../router.js";

interface PageCopy {
  eyebrow: string;
  title: string;
  description: string;
}

const pageCopy: Record<RouteName, PageCopy> = {
  overview: {
    eyebrow: "Dashboard",
    title: "Evidence overview",
    description: "Coverage metrics and recommendations will be added in WP7.",
  },
  taxonomy: {
    eyebrow: "Explore",
    title: "Themes and topics",
    description: "Browse the classifications connecting evidence to future articles.",
  },
  articles: {
    eyebrow: "Editorial",
    title: "Articles",
    description: "Generated drafts and approvals will appear here.",
  },
  article: {
    eyebrow: "Editorial",
    title: "Article",
    description: "The article review workspace will be introduced in a later package.",
  },
  forms: {
    eyebrow: "Sources",
    title: "Forms",
    description: "Register and monitor forms scanned by the poller.",
  },
  generate: {
    eyebrow: "Create",
    title: "Generate an article",
    description: "Choose evidence, coverage strategy, and a template.",
  },
  "not-found": {
    eyebrow: "404",
    title: "Page not found",
    description: "The page may have moved or the address may be incorrect.",
  },
};

export class PlaceholderPage extends HTMLElement {
  connectedCallback(): void {
    this.render();
  }

  render(): void {
    const routeName = (this.getAttribute("route") ?? "not-found") as RouteName;
    const copy = pageCopy[routeName] ?? pageCopy["not-found"];
    this.replaceChildren();

    const headingGroup = document.createElement("div");
    headingGroup.className = "page-heading";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = copy.eyebrow;
    const heading = document.createElement("h1");
    heading.tabIndex = -1;
    heading.textContent = copy.title;
    const description = document.createElement("p");
    description.className = "page-description";
    description.textContent = copy.description;
    headingGroup.append(eyebrow, heading, description);

    const panel = document.createElement("section");
    panel.className = "foundation-panel";
    panel.setAttribute("aria-labelledby", "foundation-heading");
    const panelHeading = document.createElement("h2");
    panelHeading.id = "foundation-heading";
    panelHeading.textContent = routeName === "not-found"
      ? "Return to the dashboard"
      : "Foundation ready";
    const panelText = document.createElement("p");
    panelText.textContent = routeName === "not-found"
      ? "Use the overview link to return to a known page."
      : "Navigation, responsive layout, API contracts, and accessible states are available.";
    panel.append(panelHeading, panelText);
    if (routeName === "not-found") {
      const link = document.createElement("a");
      link.href = "/";
      link.dataset.route = "";
      link.className = "text-link";
      link.textContent = "Go to overview";
      panel.append(link);
    }

    this.append(headingGroup, panel);
    requestAnimationFrame(() => heading.focus());
  }
}

customElements.define("placeholder-page", PlaceholderPage);
