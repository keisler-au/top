import type {
  GenerationJobStatus,
  GenerationStrategy,
  RecommendationStrategy,
  TaxonomyType,
} from "../api/contracts.js";

export type GenerationStep =
  | "strategy"
  | "target"
  | "evidence"
  | "template"
  | "guidance"
  | "confirm"
  | "progress";

export interface GenerationState {
  step: GenerationStep;
  strategy: GenerationStrategy;
  type: TaxonomyType;
  key: string | null;
  sourceStrategy: RecommendationStrategy | null;
  jobId: number | null;
}

const steps = new Set<GenerationStep>([
  "strategy",
  "target",
  "evidence",
  "template",
  "guidance",
  "confirm",
  "progress",
]);
const strategies = new Set<GenerationStrategy>([
  "specific",
  "most-evidence",
  "least-covered",
]);
const recommendationStrategies = new Set<RecommendationStrategy>([
  "most-evidence",
  "least-covered",
]);

function positiveInteger(value: string | null): number | null {
  if (value === null || !/^\d+$/.test(value)) return null;
  const parsed = Number.parseInt(value, 10);
  return parsed > 0 ? parsed : null;
}

export function generationState(parameters: URLSearchParams): GenerationState {
  const rawStrategy = parameters.get("strategy") as GenerationStrategy | null;
  const rawType = parameters.get("type");
  const rawStep = parameters.get("step") as GenerationStep | null;
  const rawSource = parameters.get("source_strategy") as RecommendationStrategy | null;
  const jobId = positiveInteger(parameters.get("job"));
  const key = parameters.get("key")?.trim() || null;
  const strategy = rawStrategy && strategies.has(rawStrategy)
    ? rawStrategy
    : "specific";
  const type: TaxonomyType = rawType === "topic" ? "topic" : "theme";
  let step = rawStep && steps.has(rawStep) ? rawStep : "strategy";
  if (jobId !== null) {
    step = "progress";
  } else if (step === "progress") {
    step = key ? "confirm" : "strategy";
  } else if (key && rawStep === null) {
    step = "evidence";
  }
  return {
    step,
    strategy,
    type,
    key,
    sourceStrategy: rawSource && recommendationStrategies.has(rawSource)
      ? rawSource
      : null,
    jobId,
  };
}

export function generationSearch(state: GenerationState): string {
  const parameters = new URLSearchParams({
    step: state.step,
    strategy: state.strategy,
    type: state.type,
  });
  if (state.key) parameters.set("key", state.key);
  if (state.sourceStrategy) {
    parameters.set("source_strategy", state.sourceStrategy);
  }
  if (state.jobId !== null) parameters.set("job", String(state.jobId));
  return parameters.toString();
}

export function generationPollDelay(
  pollCount: number,
  documentVisible = true,
): number {
  if (!documentVisible) return 30_000;
  return Math.min(10_000, 1_000 * (2 ** Math.min(Math.max(pollCount, 0), 4)));
}

export function generationJobIsActive(status: GenerationJobStatus): boolean {
  return status === "pending" || status === "processing";
}
