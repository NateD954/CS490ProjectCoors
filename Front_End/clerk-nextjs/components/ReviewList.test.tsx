// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { formatDate } from "@/lib/format";
import { listReviews } from "@/lib/targets-service";
import { ReviewList } from "./ReviewList";

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  loading: vi.fn(() => "toast-1"),
  dismiss: vi.fn(),
}));

vi.mock("./ui/Toast", () => ({ useToast: () => toast }));
vi.mock("@/lib/targets-service", () => ({ listReviews: vi.fn() }));

const listReviewsMock = vi.mocked(listReviews);

const DATE = "2026-10-31T12:00:00Z";
const first = { id: "r1", rating: 5, text: "Great food", date: DATE };
const second = { id: "r2", rating: 3, text: "Friendly staff", date: null };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ReviewList", () => {
  it("shows a loading message, then the reviews with their rating and date", async () => {
    listReviewsMock.mockResolvedValue({ reviews: [first, second], hasMore: false });

    render(<ReviewList targetId="t1" />);

    expect(screen.getByText(/Loading reviews/)).toBeTruthy();
    expect(await screen.findByText("Great food")).toBeTruthy();
    expect(screen.getByText("Friendly staff")).toBeTruthy();
    expect(screen.getByRole("img", { name: "5 out of 5 stars" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "3 out of 5 stars" })).toBeTruthy();
    expect(screen.getByText(formatDate(DATE))).toBeTruthy();
    expect(screen.queryByRole("button", { name: "See more reviews" })).toBeNull();
    expect(listReviewsMock).toHaveBeenCalledWith("t1", 0);
  });

  it("tells the user when there are no reviews yet", async () => {
    listReviewsMock.mockResolvedValue({ reviews: [], hasMore: false });

    render(<ReviewList targetId="t1" />);

    expect(await screen.findByText("No reviews yet. Start ingestion to collect them.")).toBeTruthy();
  });

  it("shows an error message when the reviews cannot be loaded", async () => {
    listReviewsMock.mockRejectedValue(new Error("boom"));

    render(<ReviewList targetId="t1" />);

    expect(await screen.findByText("Could not load the reviews. Refresh the page to try again.")).toBeTruthy();
  });

  it("loads the next page when See more reviews is clicked", async () => {
    listReviewsMock
      .mockResolvedValueOnce({ reviews: [first], hasMore: true })
      .mockResolvedValueOnce({ reviews: [second], hasMore: false });

    render(<ReviewList targetId="t1" />);
    fireEvent.click(await screen.findByRole("button", { name: "See more reviews" }));

    expect(await screen.findByText("Friendly staff")).toBeTruthy();
    expect(listReviewsMock).toHaveBeenLastCalledWith("t1", 1);
    expect(screen.getByText("Great food")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("button", { name: "See more reviews" })).toBeNull());
  });

  it("keeps the reviews already shown and reports an error when the next page fails", async () => {
    listReviewsMock
      .mockResolvedValueOnce({ reviews: [first], hasMore: true })
      .mockRejectedValueOnce(new Error("boom"));

    render(<ReviewList targetId="t1" />);
    fireEvent.click(await screen.findByRole("button", { name: "See more reviews" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Could not load more reviews. Please try again.")
    );
    expect(screen.getByText("Great food")).toBeTruthy();
  });
});
