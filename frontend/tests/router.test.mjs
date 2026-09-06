import test from "node:test";
import assert from "node:assert/strict";

import { legacyRedirectUrl, matchRoute, Router, routes } from "../dist/assets/router.js";

test("matches static routes and preserves query parameters", () => {
  const match = matchRoute({
    pathname: "/taxonomy/",
    search: "?type=theme&page=2",
  });

  assert.equal(match.name, "taxonomy");
  assert.equal(match.pathname, "/taxonomy");
  assert.equal(match.search.get("type"), "theme");
  assert.equal(match.search.get("page"), "2");
});

test("redirects legacy taxonomy URLs to Overview without losing state", () => {
  assert.equal(
    legacyRedirectUrl({
      pathname: "/taxonomy/",
      search: "?type=topic&search=parks&page=2",
      hash: "#coverage-heading",
    }),
    "/?type=topic&search=parks&page=2#coverage-heading",
  );
  assert.equal(
    legacyRedirectUrl({ pathname: "/templates", search: "", hash: "" }),
    "/generate",
  );
});

test("matches and decodes dynamic route parameters", () => {
  const match = matchRoute({
    pathname: "/articles/article%2042",
    search: "",
  });

  assert.equal(match.name, "article");
  assert.deepEqual(match.parameters, { id: "article 42" });
});

test("returns a stable not-found route", () => {
  const match = matchRoute({ pathname: "/missing/page", search: "" });

  assert.equal(match.name, "not-found");
  assert.equal(match.title, "Page not found");
});

test("legacy templates start generation without carrying unvalidated step state", () => {
  assert.equal(legacyRedirectUrl({
    pathname: "/templates/",
    search: "?step=template&job_id=42",
    hash: "#template",
  }), "/generate");
  assert.equal(routes.some((route) => route.pattern === "/templates"), false);
  assert.equal(matchRoute({ pathname: "/templates", search: "" }).name, "not-found");
  assert.equal(legacyRedirectUrl({ pathname: "/generate", search: "", hash: "" }), null);
  assert.equal(legacyRedirectUrl({ pathname: "/templates/42", search: "", hash: "" }), null);
});

test("router replaces legacy template history on startup and history traversal", (t) => {
  const browser = new EventTarget();
  browser.location = new URL("https://dashboard.example/templates?step=template#preview");
  const replacements = [];
  browser.history = {
    replaceState(_state, _unused, url) {
      replacements.push(url);
      browser.location = new URL(url, browser.location);
    },
    pushState() { assert.fail("compatibility redirects must replace history"); },
  };
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  Object.defineProperty(globalThis, "window", { configurable: true, value: browser });
  Object.defineProperty(globalThis, "document", { configurable: true, value: new EventTarget() });
  t.after(() => {
    router.stop();
    if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
    else delete globalThis.window;
    if (previousDocument) Object.defineProperty(globalThis, "document", previousDocument);
    else delete globalThis.document;
  });
  const router = new Router();
  const published = [];
  router.addEventListener("route-change", (event) => published.push(event.detail.name));
  router.start();
  assert.equal(router.current.name, "generate");
  assert.equal(router.current.search.size, 0);
  browser.location = new URL("https://dashboard.example/templates/");
  browser.dispatchEvent(new Event("popstate"));
  assert.deepEqual(replacements, ["/generate", "/generate"]);
  assert.deepEqual(published, ["generate", "generate"]);
});
