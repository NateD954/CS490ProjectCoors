import type { AnalysisTarget } from "./types";

// S2-020: says why Q&A is unavailable for a target, or returns undefined when questions are fine.
// Only blocks when we know the stored review count is 0. If the totals are unavailable we do
// not block, because the backend also refuses to call the AI when there are no reviews.
export function qaBlockedReason(target: AnalysisTarget | undefined): string | undefined {
  if (!target?.reviewSummary || target.reviewSummary.count > 0) return undefined;

  if (target.ingestionStatus === "in_progress") {
    return "Ingestion is still running. Questions will be available when it finishes.";
  }
  if (target.ingestionStatus === "failed") {
    return "The most recent ingestion failed and no reviews are stored. Run ingestion again before asking questions.";
  }
  return "No reviews have been ingested yet. Complete ingestion before asking ReviewLens questions.";
}
