import test from "node:test";
import assert from "node:assert/strict";

import {
  generationJobIsActive,
  generationPollDelay,
  generationSearch,
  generationState,
} from "../dist/assets/pages/generation-state.js";

test("initializes and revalidates a dashboard-provided target", () => {
  const state = generationState(new URLSearchParams(
    "strategy=specific&type=topic&key=cost%2Fbenefit&name=Untrusted"
      + "&source_strategy=least-covered",
  ));

  assert.deepEqual(state, {
    step: "evidence",
    strategy: "specific",
    type: "topic",
    key: "cost/benefit",
    sourceStrategy: "least-covered",
    jobId: null,
  });
});

test("a durable job always resumes at progress", () => {
  const state = generationState(new URLSearchParams(
    "step=template&strategy=most-evidence&type=theme&key=7&job=42",
  ));

  assert.equal(state.step, "progress");
  assert.equal(state.jobId, 42);
  assert.equal(
    generationSearch(state),
    "step=progress&strategy=most-evidence&type=theme&key=7&job=42",
  );
});

test("invalid generation URL values fall back safely", () => {
  const state = generationState(new URLSearchParams(
    "step=progress&strategy=unknown&type=other&job=-1",
  ));

  assert.deepEqual(state, {
    step: "strategy",
    strategy: "specific",
    type: "theme",
    key: null,
    sourceStrategy: null,
    jobId: null,
  });
});

test("poll delay backs off and slows while hidden", () => {
  assert.equal(generationPollDelay(0), 1_000);
  assert.equal(generationPollDelay(3), 8_000);
  assert.equal(generationPollDelay(20), 10_000);
  assert.equal(generationPollDelay(0, false), 30_000);
});

test("only non-terminal jobs continue polling", () => {
  assert.equal(generationJobIsActive("pending"), true);
  assert.equal(generationJobIsActive("processing"), true);
  assert.equal(generationJobIsActive("completed"), false);
  assert.equal(generationJobIsActive("failed"), false);
  assert.equal(generationJobIsActive("dismissed"), false);
});
