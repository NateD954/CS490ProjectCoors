// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { getTarget, startIngestion } from "@/lib/targets-service";
import { TargetWorkspace } from "./TargetWorkspace";

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  loading: vi.fn(() => "toast-1"),
  dismiss: vi.fn(),
}));

vi.mock("./ui/Toast", () => ({ useToast: () => toast }));
vi.mock("@/lib/targets-service", () => ({ getTarget: vi.fn(), startIngestion: vi.fn() }));

// The review list has its own tests, so it is replaced with a stub here.
vi.mock("./ReviewList", async () => {
  const { createElement } = await import("react");
  return {
    ReviewList: ({ targetId }: { targetId: string }) => createElement("div", null, `reviews for ${targetId}`),
  };
});

// next/link needs the Next.js router, so replace it with a plain link.
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return {
    default: ({ href, children, ...rest }: { href: string; children?: ReactNode }) =>
      createElement("a", { href, ...rest }, children),
  };
});

const getTargetMock = vi.mocked(getTarget);
const startIngestionMock = vi.mocked(startIngestion);

const URL_ = "https://www.google.com/maps/place/Sample+Coffee/data=!1s0x1:0x2";

function target(overrides: Partial<AnalysisTarget> = {}): AnalysisTarget {
  return {
    id: "t1",
    name: "Sample Coffee",
    platform: "Google Maps",
    sourceUrl: URL_,
    createdAt: "2026-10-31T12:00:00Z",
    ingestionStatus: "not_started",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TargetWorkspace: loading the target", () => {
  it("shows a loading message, then the target's details and the review list", async () => {
    getTargetMock.mockResolvedValue(target());

    render(<TargetWorkspace id="t1" />);

    expect(screen.getByText(/Loading workspace/)).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Start ingestion" })).toBeTruthy();
    expect(screen.getAllByText("Sample Coffee").length).toBeGreaterThan(0);
    expect(screen.getByText("Google Maps")).toBeTruthy();
    expect(screen.getByText(URL_).closest("a")?.getAttribute("href")).toBe(URL_);
    expect(screen.getByText("reviews for t1")).toBeTruthy();
    expect(getTargetMock).toHaveBeenCalledWith("t1");
  });

  it("replaces the placeholder with the persisted ingestion summary", async () => {
    getTargetMock.mockResolvedValue(target({
      ingestionStatus: "partial",
      skippedReviews: 2,
      reviewSummary: { count: 3, averageRating: 4 },
    }));

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByRole("heading", { name: "Ingestion summary" })).toBeTruthy();
    expect(screen.getByText("Stored reviews").nextElementSibling?.textContent).toBe("3");
    expect(screen.getByText("Average rating").nextElementSibling?.textContent).toBe("4.00 / 5");
    expect(screen.getByText("Completed with skips")).toBeTruthy();
    expect(screen.getByText("Skipped in latest run").nextElementSibling?.textContent).toBe("2");
    expect(screen.queryByText(/will appear here in a later sprint/)).toBeNull();
  });

  it("shows zero stored reviews and no rating for an empty dataset", async () => {
    getTargetMock.mockResolvedValue(target({ reviewSummary: { count: 0, averageRating: null } }));

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByText("No ratings yet")).toBeTruthy();
    expect(screen.getByText("Stored reviews").nextElementSibling?.textContent).toBe("0");
    expect(screen.getByText("Skipped in latest run").nextElementSibling?.textContent).toBe("Not recorded");
  });

  it("says the target was not found when the backend returns nothing", async () => {
    getTargetMock.mockResolvedValue(null);

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByText("This target was not found. It may have been removed.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start ingestion" })).toBeNull();
  });

  it("shows an error with a Try again button that loads the target again", async () => {
    getTargetMock.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(target());

    render(<TargetWorkspace id="t1" />);
    expect(await screen.findByText("Could not load this target. Please try again.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("button", { name: "Start ingestion" })).toBeTruthy();
    expect(getTargetMock).toHaveBeenCalledTimes(2);
  });
});

describe("TargetWorkspace: ingestion", () => {
  it("shows the failure reason and offers to run ingestion again", async () => {
    getTargetMock.mockResolvedValue(target({ ingestionStatus: "failed", ingestionMessage: "Provider down" }));

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByText("Provider down")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run ingestion again" })).toBeTruthy();
  });

  it("uses a default message when a failed ingestion has no reason", async () => {
    getTargetMock.mockResolvedValue(target({ ingestionStatus: "failed" }));

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByText("Ingestion failed. You can try again.")).toBeTruthy();
  });

  it("starts ingestion, shows the new state and reports success", async () => {
    getTargetMock.mockResolvedValue(target({ reviewSummary: { count: 0, averageRating: null } }));
    startIngestionMock.mockResolvedValue(target({
      ingestionStatus: "completed",
      skippedReviews: 0,
      reviewSummary: { count: 3, averageRating: 4 },
    }));

    render(<TargetWorkspace id="t1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Start ingestion" }));

    expect(await screen.findByRole("button", { name: "Run ingestion again" })).toBeTruthy();
    expect(startIngestionMock).toHaveBeenCalledWith("t1");
    expect(screen.getByText("Completed")).toBeTruthy();
    expect(screen.getByText("Stored reviews").nextElementSibling?.textContent).toBe("3");
    expect(screen.getByText("Average rating").nextElementSibling?.textContent).toBe("4.00 / 5");
    expect(toast.success).toHaveBeenCalledWith("Ingestion finished.");
    expect(toast.dismiss).toHaveBeenCalledWith("toast-1");
  });

  it("refreshes the persisted job state after ingestion fails", async () => {
    const failure = "Could not fetch reviews from the review provider. Please try again.";
    getTargetMock
      .mockResolvedValueOnce(target())
      .mockResolvedValueOnce(target({ ingestionStatus: "failed", ingestionMessage: failure }));
    startIngestionMock.mockRejectedValue(new Error(failure));

    render(<TargetWorkspace id="t1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Start ingestion" }));

    expect(await screen.findByText("Failed")).toBeTruthy();
    expect(screen.getByText(failure)).toBeTruthy();
    expect(getTargetMock).toHaveBeenCalledTimes(2);
    expect(toast.error).toHaveBeenCalledWith(failure);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when the failure is not an Error", async () => {
    getTargetMock.mockResolvedValue(target());
    startIngestionMock.mockRejectedValue("weird failure");

    render(<TargetWorkspace id="t1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Start ingestion" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Could not start ingestion. Please try again.")
    );
  });

  it("disables the button while ingestion is running and checks again every 3 seconds", async () => {
    const intervalSpy = vi.spyOn(globalThis, "setInterval");
    getTargetMock.mockResolvedValue(target({ ingestionStatus: "in_progress" }));

    render(<TargetWorkspace id="t1" />);

    const button = (await screen.findByRole("button", { name: /Ingestion in progress/ })) as HTMLButtonElement;
    expect(button.disabled).toBe(true);

    const poll = intervalSpy.mock.calls.find((call) => call[1] === 3000);
    expect(poll).toBeTruthy();

    // Run the timer callback by hand instead of waiting 3 real seconds.
    getTargetMock.mockResolvedValue(target({ ingestionStatus: "completed" }));
    await act(async () => {
      (poll![0] as () => void)();
    });

    expect(await screen.findByRole("button", { name: "Run ingestion again" })).toBeTruthy();
    intervalSpy.mockRestore();
  });
});
