import test from "node:test";
import assert from "node:assert/strict";

import { ApiClient } from "../dist/assets/api/client.js";
import { ApiError, userFacingError } from "../dist/assets/api/errors.js";

test("builds normalized taxonomy query parameters", async () => {
  let requestedUrl = "";
  const fakeFetch = async (url) => {
    requestedUrl = String(url);
    return Response.json({ items: [], total: 0, page: 2, page_size: 10 });
  };
  const client = new ApiClient("/api/", fakeFetch);

  await client.taxonomy({
    type: "topic",
    search: "  cost  ",
    sort: "evidence",
    direction: "desc",
    page: 2,
    pageSize: 10,
  });

  assert.equal(
    requestedUrl,
    "/api/taxonomy?type=topic&search=cost&sort=evidence&direction=desc&page=2&page_size=10",
  );
});

test("URL-encodes taxonomy keys", async () => {
  let requestedUrl = "";
  const fakeFetch = async (url) => {
    requestedUrl = String(url);
    return Response.json({});
  };
  const client = new ApiClient("", fakeFetch);

  await client.taxonomyDetail("topic", "cost/benefit");

  assert.equal(requestedUrl, "/taxonomy/topic/cost%2Fbenefit");
});

test("normalizes API problem responses", async () => {
  const fakeFetch = async () => Response.json(
    { detail: "Theme not found" },
    { status: 404 },
  );
  const client = new ApiClient("", fakeFetch);

  await assert.rejects(
    client.taxonomyDetail("theme", 99),
    (error) => error instanceof ApiError
      && error.status === 404
      && error.message === "Theme not found",
  );
  assert.equal(
    userFacingError(new ApiError(503, null, "Unavailable")),
    "The server could not complete the request. Please try again.",
  );
});

test("creates and toggles form sources with JSON requests", async () => {
  const requests = [];
  const fakeFetch = async (url, init) => {
    requests.push({ url: String(url), init });
    return Response.json({ id: 7 });
  };
  const client = new ApiClient("/api", fakeFetch);
  const payload = {
    form_id: "feedback",
    spreadsheet_id: "sheet-123",
    sheet_name: "Form Responses 1",
    ignored_headers: ["Timestamp"],
    poll_interval_seconds: 60,
    enabled: true,
  };

  await client.createFormSource(payload);
  await client.setFormSourceEnabled(7, false);

  assert.equal(requests[0].url, "/api/form-sources");
  assert.equal(requests[0].init.method, "POST");
  assert.deepEqual(JSON.parse(requests[0].init.body), payload);
  assert.equal(requests[1].url, "/api/form-sources/7/disable");
  assert.equal(requests[1].init.body, undefined);
});

test("submits and resumes durable article generation jobs", async () => {
  const requests = [];
  const fakeFetch = async (url, init) => {
    requests.push({ url: String(url), init });
    return Response.json({ id: 42, status: "pending" });
  };
  const client = new ApiClient("/api", fakeFetch);
  const payload = {
    strategy: "least-covered",
    taxonomy_type: "topic",
    taxonomy_key: "cost/benefit",
    template_version_id: 7,
    editorial_guidance: "Keep it concise.",
    evidence_ids: ["original:1", "segment:3"],
  };

  await client.createGenerationJob(payload);
  await client.generationJob(42);
  await client.retryGenerationJob(42);
  await client.dismissGenerationJob(42);

  assert.equal(requests[0].url, "/api/article-generation-jobs");
  assert.equal(requests[0].init.method, "POST");
  assert.deepEqual(JSON.parse(requests[0].init.body), payload);
  assert.equal(requests[1].url, "/api/article-generation-jobs/42");
  assert.equal(requests[1].init.method, "GET");
  assert.equal(requests[2].url, "/api/article-generation-jobs/42/retry");
  assert.equal(requests[3].url, "/api/article-generation-jobs/42/dismiss");
});

test("loads templates and requests a server-rendered preview", async () => {
  const requests = [];
  const fakeFetch = async (url, init) => {
    requests.push({ url: String(url), init });
    return Response.json([]);
  };
  const client = new ApiClient("", fakeFetch);

  await client.articleTemplates();
  await client.previewArticleTemplate(3, {
    version_id: 9,
    title: "Example",
  });

  assert.equal(requests[0].url, "/article-templates");
  assert.equal(requests[0].init.method, "GET");
  assert.equal(requests[1].url, "/article-templates/3/preview");
  assert.deepEqual(JSON.parse(requests[1].init.body), {
    version_id: 9,
    title: "Example",
  });
});

test("creates, versions, and archives templates inside generation", async () => {
  const requests = [];
  const fakeFetch = async (url, init) => {
    requests.push({ url: String(url), init });
    return Response.json({ id: 3, versions: [] });
  };
  const client = new ApiClient("/api", fakeFetch);

  await client.createArticleTemplate({
    name: "Feature",
    description: "Long-form feature",
    html_source: "<article><h1>{{title}}</h1>{{article_body}}</article>",
  });
  await client.createArticleTemplateVersion(3, {
    html_source: "<article><h1>{{title}}</h1>{{article_body}}</article>",
    created_by: "Editor",
  });
  await client.archiveArticleTemplate(3);

  assert.equal(requests[0].url, "/api/article-templates");
  assert.equal(requests[0].init.method, "POST");
  assert.equal(JSON.parse(requests[0].init.body).name, "Feature");
  assert.equal(requests[1].url, "/api/article-templates/3/versions");
  assert.equal(JSON.parse(requests[1].init.body).created_by, "Editor");
  assert.equal(requests[2].url, "/api/article-templates/3/archive");
  assert.equal(requests[2].init.body, undefined);
});

test("loads, previews, saves, and transitions an article revision", async () => {
  const requests = [];
  const fakeFetch = async (url, init) => {
    requests.push({ url: String(url), init });
    return Response.json({ items: [], rendered_html: "<article>Safe</article>" });
  };
  const client = new ApiClient("/api", fakeFetch);

  await client.articles({
    status: "ready_for_review",
    themeId: 3,
    topic: "  Cost barriers  ",
    search: "  checkout  ",
    sort: "updated",
    direction: "desc",
    page: 2,
    pageSize: 10,
  });
  await client.article(9);
  await client.articleEvidence(9);
  await client.articleHistory(9);
  await client.previewArticle(9, {
    title: "Draft",
    structured_content: { standfirst: "Summary", sections: [] },
    expected_revision_id: 12,
  });
  await client.updateArticle(9, {
    title: "Draft",
    structured_content: { standfirst: "Summary", sections: [] },
    rendered_html: "<article>Safe</article>",
    expected_revision_id: 12,
  });
  await client.transitionArticle(9, "approve", { note: "Checked" });

  assert.equal(
    requests[0].url,
    "/api/articles?status=ready_for_review&theme_id=3&topic=Cost+barriers"
      + "&search=checkout&sort=updated&direction=desc&page=2&page_size=10",
  );
  assert.equal(requests[1].url, "/api/articles/9");
  assert.equal(requests[2].url, "/api/articles/9/evidence");
  assert.equal(requests[3].url, "/api/articles/9/history");
  assert.equal(requests[4].url, "/api/articles/9/preview");
  assert.equal(requests[4].init.method, "POST");
  assert.equal(JSON.parse(requests[4].init.body).expected_revision_id, 12);
  assert.equal(requests[5].init.method, "PATCH");
  assert.equal(JSON.parse(requests[5].init.body).rendered_html, "<article>Safe</article>");
  assert.equal(requests[6].url, "/api/articles/9/approve");
  assert.deepEqual(JSON.parse(requests[6].init.body), { note: "Checked" });
});
