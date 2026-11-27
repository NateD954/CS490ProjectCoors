// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { listTargets } from "@/lib/targets-service";
import { createComparison, deleteComparison, listComparisons } from "@/lib/comparisons-service";
import { ComparisonsPageContent } from "./ComparisonsPageContent";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/targets-service", () => ({ listTargets: vi.fn() }));
vi.mock("@/lib/comparisons-service", () => ({ listComparisons: vi.fn(), deleteComparison: vi.fn(), createComparison: vi.fn() }));
const saved = { id: "c1", name: "A vs B", target_a_id: "a", target_b_id: "b", created_at: "2026-11-26T00:00:00Z" };

function load(rows = [saved]) {
  vi.mocked(listTargets).mockResolvedValue([]);
  vi.mocked(listComparisons).mockResolvedValue(rows);
  return render(<ComparisonsPageContent />);
}

afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe("saved comparisons", () => {
  it("loads the saved list on each visit and links to reopen the same comparison", async () => {
    const view = load();
    expect(screen.getByText("Loading comparisons…")).toBeTruthy();
    expect((await screen.findByRole("link", { name: "A vs B" })).getAttribute("href")).toBe("/comparisons/c1");
    view.unmount();
    render(<ComparisonsPageContent />);
    await screen.findByRole("link", { name: "A vs B" });
    expect(listComparisons).toHaveBeenCalledTimes(2);
  });

  it("shows an empty state and warns about missing references in the list", async () => {
    const view = load([]);
    expect(await screen.findByText("No saved comparisons yet.")).toBeTruthy();
    view.unmount();
    load([{ ...saved, target_a_id: null } as never]);
    expect(await screen.findByText("An analysis is unavailable.")).toBeTruthy();
  });

  it("deletes a saved comparison and removes just that row", async () => {
    vi.mocked(deleteComparison).mockResolvedValue();
    load([saved, { ...saved, id: "c2", name: "Keep this" }]);
    fireEvent.click(await screen.findByRole("button", { name: "Delete comparison A vs B" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "A vs B" })).toBeNull());
    expect(screen.getByRole("link", { name: "Keep this" })).toBeTruthy();
    expect(deleteComparison).toHaveBeenCalledWith("c1");
  });

  it("keeps the row and shows the error if deletion fails", async () => {
    vi.mocked(deleteComparison).mockRejectedValue(new Error("Could not delete. Try again."));
    load();
    fireEvent.click(await screen.findByRole("button", { name: "Delete comparison A vs B" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Could not delete. Try again.");
    expect(screen.getByRole("link", { name: "A vs B" })).toBeTruthy();
  });

  it("keeps saved comparisons usable when targets fail to load and supports retry", async () => {
    vi.mocked(listTargets).mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce([]);
    vi.mocked(listComparisons).mockResolvedValue([saved]);
    render(<ComparisonsPageContent />);
    expect(await screen.findByText("Could not load your targets. Please try again.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "A vs B" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("retries a failed list load", async () => {
    vi.mocked(listTargets).mockResolvedValue([]);
    vi.mocked(listComparisons).mockRejectedValueOnce(new Error("Session expired.")).mockResolvedValueOnce([saved]);
    render(<ComparisonsPageContent />);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Session expired.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "A vs B" })).toBeTruthy();
  });

  it("saves a comparison from owned targets and navigates to its detail page", async () => {
    vi.mocked(listTargets).mockResolvedValue(["a", "b"].map((id) => ({ id, name: `Cafe ${id}`, platform: "Google Maps", sourceUrl: "", createdAt: "2026-11-26T00:00:00Z", ingestionStatus: "not_started" })));
    vi.mocked(listComparisons).mockResolvedValue([]);
    vi.mocked(createComparison).mockResolvedValue(saved);
    render(<ComparisonsPageContent />);
    fireEvent.change(await screen.findByLabelText("Comparison name"), { target: { value: "A vs B" } });
    fireEvent.change(screen.getByLabelText("Target A"), { target: { value: "a" } });
    fireEvent.change(screen.getByLabelText("Target B"), { target: { value: "b" } });
    fireEvent.click(screen.getByRole("button", { name: "Save comparison" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/comparisons/c1"));
    expect(screen.getByRole("link", { name: "A vs B" })).toBeTruthy();
  });
});
