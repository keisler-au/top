import test from "node:test";
import assert from "node:assert/strict";

import {
  dashboardState,
  generationUrl,
  pageCount,
  stateAsQuery,
  stateAsSearch,
} from "../dist/assets/pages/dashboard-state.js";

test("reads validated dashboard state from the URL", () => {
  const state = dashboardState(new URLSearchParams(
    "type=topic&search=%20cost%20&sort=name&direction=asc&page=3&page_size=50",
  ));

  assert.deepEqual(state, {
    type: "topic",
    search: "cost",
    sort: "name",
    direction: "asc",
    page: 3,
    pageSize: 50,
  });
  assert.deepEqual(stateAsQuery(state), {
    type: "topic",
    search: "cost",
    sort: "name",
    direction: "asc",
    page: 3,
    pageSize: 50,
  });
});

test("falls back from invalid URL state and bounds page size", () => {
  const state = dashboardState(new URLSearchParams(
    "type=unknown&sort=wrong&direction=sideways&page=-1&page_size=500",
  ));

  assert.equal(state.type, "theme");
  assert.equal(state.sort, "evidence");
  assert.equal(state.direction, "desc");
  assert.equal(state.page, 1);
  assert.equal(state.pageSize, 100);

  const excessiveOffset = dashboardState(
    new URLSearchParams("page=5000&page_size=25"),
  );
  assert.equal(excessiveOffset.page, 1);
});

test("serializes shareable state and computes page count", () => {
  const search = stateAsSearch({
    type: "theme",
    search: "",
    sort: "evidence",
    direction: "desc",
    page: 2,
    pageSize: 25,
  });

  assert.equal(
    search,
    "type=theme&sort=evidence&direction=desc&page=2&page_size=25",
  );
  assert.equal(pageCount(0, 25), 1);
  assert.equal(pageCount(51, 25), 3);
});

test("generation URLs retain the exact taxonomy target and recommendation source", () => {
  assert.equal(
    generationUrl("topic", "cost/benefit", "Cost & benefit", "least-covered"),
    "/generate?strategy=specific&type=topic&key=cost%2Fbenefit"
      + "&name=Cost+%26+benefit&source_strategy=least-covered",
  );
});
