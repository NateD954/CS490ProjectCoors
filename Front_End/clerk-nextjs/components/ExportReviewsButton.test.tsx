// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AnalysisTarget } from "@/lib/types";
import { downloadReviewsCsv } from "@/lib/targets-service";
import { ExportReviewsButton } from "./ExportReviewsButton";

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  loading: vi.fn(() => "toast-1"),
  dismiss: vi.fn(),
}));

vi.mock("./ui/Toast", () => ({ useToast: () => toast }));
vi.mock("@/lib/targets-service", () => ({ downloadReviewsCsv: vi.fn() }));

const downloadMock = vi.mocked(downloadReviewsCsv);

function target(overrides: Partial<AnalysisTarget> = {}): AnalysisTarget {
  return {
    id: "t1",
    name: "Sample Coffee",
    platform: "Google Maps",
    sourceUrl: "https://www.google.com/maps/place/x/data=!1s0x1:0x2",
    createdAt: "2026-10-31T12:00:00Z",
    ingestionStatus: "completed",
    reviewSummary: { count: 3, averageRating: 4 },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const button = () => screen.getByRole("button", { name: "Download CSV" }) as HTMLButtonElement;

describe("ExportReviewsButton", () => {
  it("downloads the active target's reviews and says so", async () => {
    downloadMock.mockResolvedValue(undefined);
    const active = target();
    render(<ExportReviewsButton target={active} />);

    fireEvent.click(button());

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Reviews downloaded."));
    expect(downloadMock).toHaveBeenCalledWith(active);
  });

  it("is disabled while the file is being prepared", async () => {
    let finish!: () => void;
    downloadMock.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
    render(<ExportReviewsButton target={target()} />);

    fireEvent.click(button());

    await waitFor(() => expect(button().disabled).toBe(true));
    finish();
    await waitFor(() => expect(button().disabled).toBe(false));
  });

  it("shows the error message when the download fails", async () => {
    downloadMock.mockRejectedValue(new Error("You don't have access to this target."));
    render(<ExportReviewsButton target={target()} />);

    fireEvent.click(button());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("You don't have access to this target."));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when the failure is not an Error", async () => {
    downloadMock.mockRejectedValue("weird failure");
    render(<ExportReviewsButton target={target()} />);

    fireEvent.click(button());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not export the reviews. Please try again."));
  });

  it("is disabled, and says why, when the target has no stored reviews", () => {
    render(<ExportReviewsButton target={target({ reviewSummary: { count: 0, averageRating: null } })} />);

    expect(button().disabled).toBe(true);
    expect(screen.getByText("No reviews to export yet.")).toBeTruthy();
    fireEvent.click(button());
    expect(downloadMock).not.toHaveBeenCalled();
  });

  it("stays available when the review totals are not known", () => {
    render(<ExportReviewsButton target={target({ reviewSummary: undefined })} />);

    expect(button().disabled).toBe(false);
  });
});
