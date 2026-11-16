import { describe, expect, it } from "vitest";
import type { AnalysisTarget } from "./types";
import { qaBlockedReason } from "./qa-state";

function target(overrides: Partial<AnalysisTarget> = {}): AnalysisTarget {
  return {
    id: "t1",
    name: "Sample Coffee",
    platform: "Google Maps",
    sourceUrl: "u",
    createdAt: "2026-10-31T12:00:00Z",
    ingestionStatus: "completed",
    reviewSummary: { count: 0, averageRating: null },
    ...overrides,
  };
}

// S2-020: Q&A is blocked only when we know the target has no stored reviews.
describe("qaBlockedReason", () => {
  it("blocks a target that was never ingested", () => {
    expect(qaBlockedReason(target({ ingestionStatus: "not_started" }))).toMatch(/No reviews have been ingested/);
  });

  it("blocks a target whose ingestion finished with zero reviews", () => {
    expect(qaBlockedReason(target({ ingestionStatus: "completed" }))).toMatch(/Complete ingestion/);
  });

  it("says the last ingestion failed when it failed and nothing is stored", () => {
    expect(qaBlockedReason(target({ ingestionStatus: "failed" }))).toMatch(/most recent ingestion failed/);
  });

  it("says ingestion is still running while it runs", () => {
    expect(qaBlockedReason(target({ ingestionStatus: "in_progress" }))).toMatch(/still running/);
  });

  it("allows questions when reviews are stored", () => {
    expect(qaBlockedReason(target({ reviewSummary: { count: 3, averageRating: 4 } }))).toBeUndefined();
  });

  it("allows questions when reviews are stored even if the latest run failed", () => {
    expect(
      qaBlockedReason(target({ ingestionStatus: "failed", reviewSummary: { count: 3, averageRating: 4 } }))
    ).toBeUndefined();
  });

  it("does not block when the totals are unavailable or the target is not loaded yet", () => {
    expect(qaBlockedReason(target({ reviewSummary: undefined }))).toBeUndefined();
    expect(qaBlockedReason(undefined)).toBeUndefined();
  });
});
