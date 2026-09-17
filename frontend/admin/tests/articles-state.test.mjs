import test from "node:test";
import assert from "node:assert/strict";

import {
  articleReturnUrl,
  articlesQuery,
  articlesSearch,
  articlesState,
} from "../dist/assets/pages/articles-state.js";
import {
  editableArticleContent,
  paragraphsFromText,
  parseThemeIds,
  parseTopicNames,
} from "../dist/assets/pages/article-detail-state.js";

test("article library state validates and round-trips URL filters", () => {
  const state = articlesState(new URLSearchParams(
    "status=ready_for_review&theme_id=7&topic=Cost%20Barriers&search=checkout"
      + "&sort=title&direction=asc&page=3&page_size=10",
  ));

  assert.deepEqual(articlesQuery(state), {
    status: "ready_for_review",
    themeId: 7,
    topic: "Cost Barriers",
    search: "checkout",
    sort: "title",
    direction: "asc",
    page: 3,
    pageSize: 10,
  });
  assert.equal(
    articlesSearch(state),
    "sort=title&direction=asc&page=3&page_size=10&status=ready_for_review"
      + "&theme_id=7&topic=Cost+Barriers&search=checkout",
  );
});

test("article return URLs are restricted to the local library", () => {
  globalThis.window = { location: { origin: "https://dashboard.test" } };
  assert.equal(
    articleReturnUrl(new URLSearchParams(
      "return=%2Farticles%3Fstatus%3Dapproved%26page%3D2",
    )),
    "/articles?status=approved&page=2",
  );
  assert.equal(
    articleReturnUrl(new URLSearchParams(
      "return=https%3A%2F%2Fevil.test%2Farticles",
    )),
    "/articles",
  );
});

test("structured editor normalizes content without accepting raw shapes", () => {
  assert.deepEqual(editableArticleContent({
    standfirst: "Summary",
    sections: [{
      heading: "Finding",
      paragraphs: ["One", 2, "Two"],
      evidence_ids: ["original:1", null],
    }],
  }), {
    standfirst: "Summary",
    sections: [{
      heading: "Finding",
      paragraphs: ["One", "Two"],
      evidence_ids: ["original:1"],
    }],
  });
  assert.deepEqual(paragraphsFromText(" First \n\n Second\nline \n\n"), [
    "First", "Second\nline",
  ]);
});

test("tag parsing deduplicates values and rejects invalid theme IDs", () => {
  assert.deepEqual(parseThemeIds("7, 2, 7"), [7, 2]);
  assert.deepEqual(parseTopicNames("Cost barriers\nCheckout friction, Cost barriers"), [
    "Cost barriers", "Checkout friction",
  ]);
  assert.throws(() => parseThemeIds("7, nope"), /positive whole numbers/);
});
