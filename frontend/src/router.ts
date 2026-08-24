export type RouteName =
  | "overview"
  | "taxonomy"
  | "articles"
  | "article"
  | "templates"
  | "forms"
  | "generate"
  | "not-found";

export interface RouteDefinition {
  name: RouteName;
  pattern: string;
  title: string;
}

export interface RouteMatch extends RouteDefinition {
  pathname: string;
  parameters: Readonly<Record<string, string>>;
  search: URLSearchParams;
}

export const routes: readonly RouteDefinition[] = [
  { name: "overview", pattern: "/", title: "Overview" },
  { name: "taxonomy", pattern: "/taxonomy", title: "Themes & topics" },
  { name: "articles", pattern: "/articles", title: "Articles" },
  { name: "article", pattern: "/articles/:id", title: "Article" },
  { name: "templates", pattern: "/templates", title: "Templates" },
  { name: "forms", pattern: "/forms", title: "Forms" },
  { name: "generate", pattern: "/generate", title: "Generate article" },
] as const;

function normalizedPath(pathname: string): string {
  if (pathname === "/") {
    return pathname;
  }
  return pathname.replace(/\/+$/, "") || "/";
}

export function matchRoute(location: Pick<Location, "pathname" | "search">): RouteMatch {
  const pathname = normalizedPath(location.pathname);
  const pathSegments = pathname.split("/").filter(Boolean);
  for (const route of routes) {
    const patternSegments = route.pattern.split("/").filter(Boolean);
    if (patternSegments.length !== pathSegments.length) {
      continue;
    }
    const parameters: Record<string, string> = {};
    let matches = true;
    for (let index = 0; index < patternSegments.length; index += 1) {
      const pattern = patternSegments[index];
      const segment = pathSegments[index];
      if (pattern === undefined || segment === undefined) {
        matches = false;
        break;
      }
      if (pattern.startsWith(":")) {
        try {
          parameters[pattern.slice(1)] = decodeURIComponent(segment);
        } catch {
          matches = false;
          break;
        }
      } else if (pattern !== segment) {
        matches = false;
        break;
      }
    }
    if (matches) {
      return {
        ...route,
        pathname,
        parameters,
        search: new URLSearchParams(location.search),
      };
    }
  }
  return {
    name: "not-found",
    pattern: pathname,
    pathname,
    title: "Page not found",
    parameters: {},
    search: new URLSearchParams(location.search),
  };
}

export class Router extends EventTarget {
  #current: RouteMatch;

  constructor() {
    super();
    this.#current = matchRoute(window.location);
  }

  get current(): RouteMatch {
    return this.#current;
  }

  start(): void {
    window.addEventListener("popstate", this.#handleLocationChange);
    document.addEventListener("click", this.#handleDocumentClick);
    this.#publish();
  }

  stop(): void {
    window.removeEventListener("popstate", this.#handleLocationChange);
    document.removeEventListener("click", this.#handleDocumentClick);
  }

  navigate(url: string, options: { replace?: boolean } = {}): void {
    const destination = new URL(url, window.location.href);
    if (destination.origin !== window.location.origin) {
      window.location.assign(destination);
      return;
    }
    const method = options.replace ? "replaceState" : "pushState";
    window.history[method]({}, "", destination);
    this.#publish();
  }

  readonly #handleLocationChange = (): void => {
    this.#publish();
  };

  readonly #handleDocumentClick = (event: MouseEvent): void => {
    if (
      event.defaultPrevented
      || event.button !== 0
      || event.metaKey
      || event.ctrlKey
      || event.shiftKey
      || event.altKey
    ) {
      return;
    }
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const link = target.closest<HTMLAnchorElement>("a[data-route]");
    if (!link || link.target || link.hasAttribute("download")) {
      return;
    }
    const destination = new URL(link.href, window.location.href);
    if (destination.origin !== window.location.origin) {
      return;
    }
    event.preventDefault();
    this.navigate(`${destination.pathname}${destination.search}${destination.hash}`);
  };

  #publish(): void {
    this.#current = matchRoute(window.location);
    this.dispatchEvent(
      new CustomEvent<RouteMatch>("route-change", {
        detail: this.#current,
      }),
    );
  }
}
