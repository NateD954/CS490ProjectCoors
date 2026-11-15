// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AnalysisTarget } from "@/lib/types";
import { getTarget, listTargets, startIngestion } from "@/lib/targets-service";
import ReviewQA from "./ReviewQA";
import { TargetPageContent } from "./TargetPageContent";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("./ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), loading: vi.fn(() => "x"), dismiss: vi.fn() }),
}));
vi.mock("@clerk/nextjs", () => ({ useAuth: () => ({ getToken: async () => "tok" }) }));
vi.mock("@/lib/targets-service", () => ({ getTarget: vi.fn(), listTargets: vi.fn(), startIngestion: vi.fn() }));
vi.mock("./ReviewList", async () => {
  const { createElement } = await import("react");
  return { ReviewList: () => createElement("div", null, "reviews") };
});
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return { default: ({ href, children }: { href: string; children?: React.ReactNode }) => createElement("a", { href }, children) };
});

const getTargetMock = vi.mocked(getTarget);
const listMock = vi.mocked(listTargets);
const startMock = vi.mocked(startIngestion);
const PLACEHOLDER = "Ask a question about these reviews...";

function t(overrides: Partial<AnalysisTarget> = {}): AnalysisTarget {
  return {
    id: "a",
    name: "Coffee A",
    platform: "Google Maps",
    sourceUrl: "u",
    createdAt: "2026-10-31T12:00:00Z",
    ingestionStatus: "not_started",
    reviewSummary: { count: 0, averageRating: null },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

// S2-020: a target with no stored reviews must not look like normal Q&A.
describe("ReviewQA with no review data", () => {
  it("shows the reason and disables the question box and Ask button", () => {
    render(<ReviewQA targetId="a" blockedReason="No reviews have been ingested yet. Complete ingestion before asking ReviewLens questions." />);

    expect(screen.getByRole("status").textContent).toContain("Complete ingestion");
    expect((screen.getByPlaceholderText(PLACEHOLDER) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("never sends a question, even if the form is submitted anyway", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<ReviewQA targetId="a" blockedReason="No reviews yet." />);

    fireEvent.submit(container.querySelector("form")!);

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows no notice when the target has reviews", () => {
    render(<ReviewQA targetId="a" />);

    expect(screen.queryByRole("status")).toBeNull();
    expect((screen.getByPlaceholderText(PLACEHOLDER) as HTMLInputElement).disabled).toBe(false);
  });
});

describe("Target page with no review data", () => {
  it("blocks Q&A for a target that was never ingested", async () => {
    getTargetMock.mockResolvedValue(t());
    listMock.mockResolvedValue([t()]);

    render(<TargetPageContent id="a" />);

    expect((await screen.findByRole("status")).textContent).toContain("No reviews have been ingested");
    expect((screen.getByPlaceholderText(PLACEHOLDER) as HTMLInputElement).disabled).toBe(true);
  });

  it("says the last ingestion failed when it failed and nothing is stored", async () => {
    getTargetMock.mockResolvedValue(t({ ingestionStatus: "failed", ingestionMessage: "Provider down" }));
    listMock.mockResolvedValue([t()]);

    render(<TargetPageContent id="a" />);

    expect((await screen.findByRole("status")).textContent).toContain("most recent ingestion failed");
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("unlocks Q&A as soon as ingestion stores reviews", async () => {
    getTargetMock.mockResolvedValue(t());
    listMock.mockResolvedValue([t()]);
    startMock.mockResolvedValue(t({ ingestionStatus: "completed", reviewSummary: { count: 3, averageRating: 4 } }));

    render(<TargetPageContent id="a" />);
    await screen.findByRole("status");
    fireEvent.click(screen.getByRole("button", { name: "Start ingestion" }));

    await screen.findByRole("button", { name: "Run ingestion again" });
    expect(screen.queryByRole("status")).toBeNull();
    expect((screen.getByPlaceholderText(PLACEHOLDER) as HTMLInputElement).disabled).toBe(false);
  });

  it("leaves Q&A open for a target that has reviews", async () => {
    getTargetMock.mockResolvedValue(t({ ingestionStatus: "completed", reviewSummary: { count: 3, averageRating: 4 } }));
    listMock.mockResolvedValue([t()]);

    render(<TargetPageContent id="a" />);
    await screen.findByRole("button", { name: "Run ingestion again" });

    expect(screen.queryByRole("status")).toBeNull();
    expect((screen.getByPlaceholderText(PLACEHOLDER) as HTMLInputElement).disabled).toBe(false);
  });
});
