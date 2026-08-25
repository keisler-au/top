import test from "node:test";
import assert from "node:assert/strict";

import {
  generationHref,
  primaryNavigation,
} from "../dist/assets/navigation.js";

test("primary navigation excludes duplicate taxonomy and template destinations", () => {
  assert.deepEqual(
    primaryNavigation.map(({ href, label, route }) => ({ href, label, route })),
    [
      { href: "/", label: "Overview", route: "overview" },
      { href: "/articles", label: "Articles", route: "articles" },
      { href: "/forms", label: "Forms", route: "forms" },
    ],
  );
  assert.equal(generationHref, "/generate");
});
