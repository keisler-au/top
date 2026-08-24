import test from "node:test";
import assert from "node:assert/strict";

import { matchRoute } from "../dist/assets/router.js";

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
