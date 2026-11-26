// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AnalysisTarget } from "@/lib/types";
import { downloadAnalysisMarkdown } from "@/lib/targets-service";
import { ExportAnalysisButton } from "./ExportAnalysisButton";

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  loading: vi.fn(() => "toast-1"),
  dismiss: vi.fn(),
}));

vi.mock("./ui/Toast", () => ({ useToast: () => toast }));
vi.mock("@/lib/targets-service", () => ({ downloadAnalysisMarkdown: vi.fn() }));

const downloadMock = vi.mocked(downloadAnalysisMarkdown);

const active: AnalysisTarget = {
  id: "t1",
  name: "Sample Coffee",
  platform: "Google Maps",
  sourceUrl: "https://www.google.com/maps/place/x/data=!1s0x1:0x2",
  createdAt: "2026-10-31T12:00:00Z",
  ingestionStatus: "completed",
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const button = () => screen.getByRole("button", { name: "Download Markdown" }) as HTMLButtonElement;

describe("ExportAnalysisButton", () => {
  it("downloads the active analysis and says so", async () => {
    downloadMock.mockResolvedValue(undefined);
    render(<ExportAnalysisButton target={active} />);

    fireEvent.click(button());

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Analysis downloaded."));
    expect(downloadMock).toHaveBeenCalledWith(active);
  });

  it("is disabled while the file is being prepared", async () => {
    let finish!: () => void;
    downloadMock.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
    render(<ExportAnalysisButton target={active} />);

    fireEvent.click(button());

    await waitFor(() => expect(button().disabled).toBe(true));
    finish();
    await waitFor(() => expect(button().disabled).toBe(false));
  });

  it("shows the error message when the download fails", async () => {
    downloadMock.mockRejectedValue(new Error("You don't have access to this target."));
    render(<ExportAnalysisButton target={active} />);

    fireEvent.click(button());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("You don't have access to this target."));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when the failure is not an Error", async () => {
    downloadMock.mockRejectedValue("weird failure");
    render(<ExportAnalysisButton target={active} />);

    fireEvent.click(button());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not export the analysis. Please try again."));
  });
});
