// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { TargetWorkspace } from "./TargetWorkspace";

// S3-004: reopening a saved analysis. Nothing in the page is remembered from an earlier visit.
// The real service and the real review list run. Only the network is replaced, with what the
// backend sends for an analysis that was saved earlier (its real field names).
vi.mock("./ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), loading: vi.fn(() => "t"), dismiss: vi.fn() }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return { default: ({ href, children, ...rest }: { href: string; children?: ReactNode }) => createElement("a", { href, ...rest }, children) };
});

const SOURCE = "https://www.google.com/maps/place/Corner+Cafe/data=!1s0x1:0x2";

const savedRow = {
  id: "t1",
  business_name: "Corner cafe",
  platform: "GOOGLE_MAPS",
  source_url: SOURCE,
  created_at: "2026-10-31T12:00:00Z",
  ingestion_status: "partial",
  ingestion_error: null,
  ingestion_skipped: 2,
  current_ingestion_id: "job-1",
  current_ingestion_at: "2026-11-02T10:00:00Z",
  review_summary: { review_count: 3, average_rating: 4 },
};

const savedReviews = [
  { id: "r2", rating: 5, review_text: "Espresso is great", reviewed_at: "2026-10-03T10:00:00Z" },
  { id: "r1", rating: 4, review_text: "Pastries are fresh", reviewed_at: "2026-10-01T10:00:00Z" },
  { id: "r3", rating: 3, review_text: "No date on this one", reviewed_at: null },
];

const fetchMock = vi.fn();

function serverHas(row: object | null, reviews: object[] = savedReviews) {
  fetchMock.mockImplementation(async (url: string) => {
    if (row === null) return { ok: false, status: 404, json: async () => ({ detail: "Target not found." }) };
    const body = url.includes("/reviews") ? reviews : row;
    return { ok: true, status: 200, json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("reopening a saved analysis", () => {
  it("restores the name and the source", async () => {
    serverHas(savedRow);

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByRole("heading", { name: "Corner cafe" })).toBeTruthy();
    expect(screen.getByText("Google Maps")).toBeTruthy();
    expect(screen.getByText(SOURCE).closest("a")?.getAttribute("href")).toBe(SOURCE);
  });

  it("restores the ingestion state and its summary", async () => {
    serverHas(savedRow);

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByText("Completed with skips")).toBeTruthy();
    expect(screen.getByText("Stored reviews").nextElementSibling?.textContent).toBe("3");
    expect(screen.getByText("Average rating").nextElementSibling?.textContent).toBe("4.00 / 5");
    expect(screen.getByText("Skipped in latest run").nextElementSibling?.textContent).toBe("2");
    expect(screen.getByText(/Last successful ingestion:/)).toBeTruthy();
  });

  it("restores the stored reviews, newest first, without running ingestion again", async () => {
    serverHas(savedRow);

    render(<TargetWorkspace id="t1" />);

    const first = await screen.findByText("Espresso is great");
    const second = screen.getByText("Pastries are fresh");
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("No date on this one")).toBeTruthy();
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method && init.method !== "GET");
    expect(posts).toEqual([]); // opening only reads
  });

  it("shows the reason and keeps the saved reviews when the last refresh failed", async () => {
    serverHas({ ...savedRow, ingestion_status: "failed", ingestion_error: "The review provider could not be reached." });

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByText("The review provider could not be reached.")).toBeTruthy();
    expect(screen.getByText(/Your saved reviews are still available/)).toBeTruthy();
    expect(await screen.findByText("Espresso is great")).toBeTruthy();
  });

  it("reopens an analysis that was never ingested as not started and empty", async () => {
    serverHas(
      { ...savedRow, ingestion_status: "not_started", ingestion_skipped: null, current_ingestion_id: null, current_ingestion_at: null, review_summary: { review_count: 0, average_rating: null } },
      []
    );

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByRole("button", { name: "Start ingestion" })).toBeTruthy();
    expect(screen.getByText("No ratings yet")).toBeTruthy();
    expect(await screen.findByText(/No reviews yet/)).toBeTruthy();
  });

  it("says so when the analysis is not found", async () => {
    serverHas(null);

    render(<TargetWorkspace id="t1" />);

    expect(await screen.findByText("This target was not found. It may have been removed.")).toBeTruthy();
  });
});
