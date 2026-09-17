import test from "node:test";
import assert from "node:assert/strict";

import { QueryStore } from "../dist/assets/state/query-store.js";

test("deduplicates concurrent requests and caches the value", async () => {
  const store = new QueryStore();
  let calls = 0;
  const loader = async () => {
    calls += 1;
    await Promise.resolve();
    return { evidence: 12 };
  };

  const [first, second] = await Promise.all([
    store.fetch("summary", loader),
    store.fetch("summary", loader),
  ]);
  const cached = await store.fetch("summary", loader);

  assert.equal(calls, 1);
  assert.strictEqual(first, second);
  assert.strictEqual(first, cached);
});

test("invalidates keys by prefix", async () => {
  const store = new QueryStore();
  let calls = 0;
  const loader = async () => ++calls;

  await store.fetch("taxonomy:topic", loader);
  store.invalidate("taxonomy:");
  const refreshed = await store.fetch("taxonomy:topic", loader);

  assert.equal(refreshed, 2);
});

test("does not cache rejected requests", async () => {
  const store = new QueryStore();
  let calls = 0;
  const loader = async () => {
    calls += 1;
    if (calls === 1) throw new Error("temporary");
    return "ready";
  };

  await assert.rejects(store.fetch("key", loader), /temporary/);
  assert.equal(await store.fetch("key", loader), "ready");
  assert.equal(calls, 2);
});
