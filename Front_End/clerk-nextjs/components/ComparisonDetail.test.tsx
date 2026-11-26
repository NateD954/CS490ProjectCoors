// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { deleteComparison, getComparison, type ComparisonDataset, type ComparisonDetail as Detail } from "@/lib/comparisons-service";
import { ComparisonDetail } from "./ComparisonDetail";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/comparisons-service", () => ({ getComparison: vi.fn(), deleteComparison: vi.fn() }));
const dataset: ComparisonDataset = {
  id: "a", unavailable: false, business_name: "Cafe A", platform: "GOOGLE_MAPS", source_url: "https://google.com/a",
  review_summary: { review_count: 26, average_rating: 3.5 }, ingestion_status: "completed", ingestion_error: null, ingestion_skipped: 0,
  sample_reviews: [{ id: "r1", rating: 5, review_text: "Great coffee", reviewed_at: "2026-11-25T00:00:00Z" }],
};
const saved: Detail = {
  id: "c1", name: "A vs B", target_a_id: "a", target_b_id: "b", created_at: "2026-11-26T00:00:00Z", target_a: dataset,
  target_b: { ...dataset, id: "b", business_name: "Cafe B", review_summary: { review_count: 0, average_rating: null }, ingestion_status: "not_started", ingestion_skipped: null, sample_reviews: [] },
};

function load(detail = saved) {
  vi.mocked(getComparison).mockResolvedValue(detail);
  return render(<ComparisonDetail id="c1" />);
}

afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe("comparison detail", () => {
  it("reopens both datasets and shows stored metrics, status, samples and workspace links", async () => {
    load();
    expect(screen.getByRole("status").textContent).toBe("Loading comparison…");
    await screen.findByRole("heading", { name: "A vs B" });
    const a = within(screen.getByRole("heading", { name: "Target A" }).parentElement!);
    const b = within(screen.getByRole("heading", { name: "Target B" }).parentElement!);
    expect(a.getByText("26")).toBeTruthy();
    expect(a.getByText("3.50 / 5")).toBeTruthy();
    expect(a.getByText("Completed")).toBeTruthy();
    expect(a.getByText("Great coffee")).toBeTruthy();
    expect(b.getByText("No ratings yet")).toBeTruthy();
    expect(b.getByText("No stored reviews yet.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open Cafe A workspace" }).getAttribute("href")).toBe("/targets/a");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(getComparison).toHaveBeenCalledWith("c1");
  });

  it.each(["target_a", "target_b", "both"])("keeps the comparison readable when %s is unavailable", async (slot) => {
    const missing: ComparisonDataset = { id: null, unavailable: true, reason: "unavailable" };
    load({ ...saved, target_a: slot !== "target_b" ? missing : saved.target_a, target_b: slot !== "target_a" ? missing : saved.target_b });
    expect((await screen.findByRole("alert")).textContent).toMatch(/One or both analyses are unavailable/);
    expect(screen.getByRole("heading", { name: "A vs B" })).toBeTruthy();
    if (slot === "target_b") expect(screen.getByText("Great coffee")).toBeTruthy();
    if (slot === "target_a") expect(screen.getByRole("heading", { name: "Cafe B" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete comparison" })).toBeTruthy();
  });

  it("can reload a temporarily unavailable dataset", async () => {
    load({ ...saved, target_a: { id: "a", unavailable: true, reason: "temporarily_unavailable" } });
    expect(await screen.findByText(/This analysis could not be loaded right now/)).toBeTruthy();
    vi.mocked(getComparison).mockResolvedValue(saved);
    fireEvent.click(screen.getByRole("button", { name: "Reload comparison" }));
    expect(await screen.findByText("Great coffee")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows an ingestion error alongside retained reviews and handles empty review text", async () => {
    load({ ...saved, target_a: { ...dataset, ingestion_status: "failed", ingestion_error: "Refresh failed. Try again.", sample_reviews: [{ id: "empty", rating: 3, review_text: null, reviewed_at: null }] } });
    expect(await screen.findByText("Refresh failed. Try again.")).toBeTruthy();
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.getByText("No written review.")).toBeTruthy();
  });

  it("deletes the comparison and returns to the list", async () => {
    vi.mocked(deleteComparison).mockResolvedValue();
    load();
    fireEvent.click(await screen.findByRole("button", { name: "Delete comparison" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/comparisons"));
    expect(deleteComparison).toHaveBeenCalledWith("c1");
  });

  it("leaves data visible and allows another delete attempt after an API error", async () => {
    vi.mocked(deleteComparison).mockRejectedValueOnce(new Error("Delete failed.")).mockResolvedValueOnce();
    load();
    fireEvent.click(await screen.findByRole("button", { name: "Delete comparison" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Delete failed.");
    expect(screen.getByText("Great coffee")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Delete comparison" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/comparisons"));
  });

  it("shows a failed reopen and can retry", async () => {
    vi.mocked(getComparison).mockRejectedValueOnce(new Error("Comparison not found.")).mockResolvedValueOnce(saved);
    render(<ComparisonDetail id="c1" />);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Comparison not found.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Great coffee")).toBeTruthy();
  });

  it("discards late responses and clears old data when a different comparison opens", async () => {
    let resolve!: (value: Detail) => void;
    vi.mocked(getComparison).mockReturnValueOnce(new Promise((done) => { resolve = done; })).mockResolvedValueOnce({ ...saved, id: "c2", name: "New comparison" });
    const view = render(<ComparisonDetail id="c1" />);
    view.rerender(<ComparisonDetail id="c2" />);
    await screen.findByRole("heading", { name: "New comparison" });
    resolve(saved);
    await waitFor(() => expect(screen.queryByRole("heading", { name: "A vs B" })).toBeNull());
  });
});
