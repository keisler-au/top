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
  assert.match(
    userFacingError(new ApiError(503, { detail: { code: "taxonomy_first_run" } }, "Unavailable")),
    /No taxonomy has been published/,
  );
  assert.match(
    userFacingError(new ApiError(503, { detail: { code: "taxonomy_candidate_failed" } }, "Unavailable")),
    /inspect the failed stage/ ,
  );
  assert.match(
    userFacingError(new ApiError(503, { detail: { code: "taxonomy_quality_blocked" } }, "Unavailable")),
    /completed processing, consistent evidence links, and at least one valid topic/,
  );
  assert.match(
    userFacingError(new ApiError(503, { detail: { code: "taxonomy_candidate_processing" } }, "Unavailable")),
    /candidate is processing/,
  );
  assert.match(
    userFacingError(new ApiError(503, { detail: { code: "taxonomy_automation_blocked" } }, "Unavailable")),
    /blocked/,
  );
  assert.match(
    userFacingError(new ApiError(503, { detail: { code: "taxonomy_scheduler_unavailable" } }, "Unavailable")),
    /scheduler is unavailable/,
  );
});

test("dashboard request keeps bounded first-run failure code for user feedback", async () => {
  const client = new ApiClient("/api", async () => Response.json(
    { detail: { code: "taxonomy_candidate_failed" } },
    { status: 503 },
  ));
  await assert.rejects(client.summary(), (error) =>
    error instanceof ApiError
    && error.status === 503
    && /inspect the failed stage/.test(userFacingError(error))
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

test("taxonomy review reads need no credentials and preserve request cancellation", async () => {
  const calls = [];
  const client = new ApiClient('/api', async (url, init) => {
    calls.push({url,init});
    return new Response(JSON.stringify([]), {status:200,headers:{'Content-Type':'application/json'}});
  });
  const controller = new AbortController();
  const options = {signal:controller.signal};
  await client.taxonomyRuns(options);
  await client.taxonomyRun(6, options);
  await client.taxonomyTopicEvidence(6,11,50,options);
  await client.inputs();
  assert.deepEqual(calls.map(c => c.url), ['/api/taxonomy-runs','/api/taxonomy-runs/6',
    '/api/taxonomy-runs/6/topics/11/evidence?offset=50','/api/inputs?offset=0&limit=50']);
  assert.ok(calls.slice(0,3).every(c => c.init.headers.Authorization === undefined && c.init.signal === controller.signal));
  assert.equal(calls[3].init.headers.Authorization,undefined);
  assert.ok(calls.every(c => !c.url.includes('secret')));
});


test("encodes input filters while preserving false presence and cancellation", async () => {
  let request;
  const client = new ApiClient('/api', async (url, init) => {
    request = {url, init};
    return new Response('[]', {status:200,headers:{'Content-Type':'application/json'}});
  });
  const signal = new AbortController().signal;
  await client.inputs(50, {signal}, {search:' 50% & fees ',status:'completed',has_topic:false,
    source:'sheets',form_key:'My form',question_key:'Q1',question_version:2,
    submission_key:'row:2',topic:'cost',theme:'access',created_from:'2026-01-01',created_to:'2026-02-01'});
  const params = new URL(request.url,'http://test').searchParams;
  assert.equal(params.get('search'),'50% & fees');
  assert.equal(params.get('has_topic'),'false');
  assert.equal(params.get('offset'),'50');
  assert.equal(params.get('form_key'),'My form');
  assert.equal(params.get('question_version'),'2');
  assert.equal(params.get('status'),'completed');
  assert.equal(params.get('created_to'),'2026-02-01');
  assert.equal(request.init.signal,signal);
  await client.inputs(0,undefined,{topic:' ',search:undefined});
  assert.equal(request.url,'/api/inputs?offset=0&limit=50');
});
