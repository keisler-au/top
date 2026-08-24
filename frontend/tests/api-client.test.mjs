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
