import test from "node:test";
import assert from "node:assert/strict";

import {
  activeGenerationMessage,
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

test("active jobs have explicit article-creation copy", () => {
  assert.deepEqual(activeGenerationMessage("pending"), {
    title: "Article creation is queued",
    description: "Your request has been saved. The generation worker will start creating a reviewable draft shortly.",
    loadingLabel: "Waiting for the article generation worker…",
  });
  assert.deepEqual(activeGenerationMessage("processing"), {
    title: "Article creation is in progress",
    description: "The generation worker is writing and validating your reviewable draft. This can take a minute or two.",
    loadingLabel: "Creating and validating the article draft…",
  });
  assert.equal(activeGenerationMessage("completed"), null);
  assert.equal(activeGenerationMessage("failed"), null);
});
