// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AnalysisTarget } from "@/lib/types";
import { getTarget, listTargets } from "@/lib/targets-service";
import { renameTarget } from "@/lib/rename-service";
import { TargetPageContent } from "./TargetPageContent";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("./ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), loading: vi.fn(() => "x"), dismiss: vi.fn() }),
}));
vi.mock("@clerk/nextjs", () => ({ useAuth: () => ({ getToken: async () => "tok" }) }));
vi.mock("@/lib/targets-service", () => ({ getTarget: vi.fn(), listTargets: vi.fn(), startIngestion: vi.fn() }));
vi.mock("@/lib/rename-service", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/rename-service")>()),
  renameTarget: vi.fn(),
}));
vi.mock("./ReviewList", async () => {
  const { createElement } = await import("react");
  return { ReviewList: ({ targetId }: { targetId: string }) => createElement("div", null, `reviews for ${targetId}`) };
});
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return { default: ({ href, children }: { href: string; children?: React.ReactNode }) => createElement("a", { href }, children) };
});

const getTargetMock = vi.mocked(getTarget);
const listMock = vi.mocked(listTargets);
const renameMock = vi.mocked(renameTarget);

function target(id: string, name: string): AnalysisTarget {
  return {
    id, name, platform: "Google Maps", sourceUrl: "https://www.google.com/maps/place/Chipotle", createdAt: "2026-10-31T12:00:00Z",
    ingestionStatus: "completed", reviewSummary: { count: 3, averageRating: 4 },
  };
}
const A = target("a", "Downtown lunch");
const B = target("b", "Airport kiosk");

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// The Active target line inside the Q&A box.
function qaActiveTarget() {
  return screen.getByText("Ask ReviewLens AI").parentElement!.textContent ?? "";
}

// S3-002: after a rename, the new name appears everywhere the old one was.
describe("Renaming from the workspace", () => {
  it("updates the title, summary, Q&A and dropdown, and leaves the source and other analyses alone", async () => {
    getTargetMock.mockImplementation(async (id) => (id === "a" ? A : B));
    listMock.mockResolvedValue([A, B]);
    renameMock.mockResolvedValue("Lunch spot downtown");

    render(<TargetPageContent id="a" />);
    await screen.findByText("reviews for a");
    fireEvent.click(screen.getByRole("button", { name: "Rename this analysis" }));
    fireEvent.change(screen.getByLabelText("New name"), { target: { value: "Lunch spot downtown" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "Lunch spot downtown" })).toBeTruthy());
    expect(qaActiveTarget()).toContain("Lunch spot downtown");
    expect(screen.getByRole("option", { name: "Lunch spot downtown" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "Downtown lunch" })).toBeNull();
    expect(screen.getByRole("option", { name: "Airport kiosk" })).toBeTruthy(); // the other analysis is untouched
    expect(screen.getByText("reviews for a")).toBeTruthy(); // same reviews, same analysis
    expect(screen.getByRole("link", { name: "https://www.google.com/maps/place/Chipotle" })).toBeTruthy(); // same source
  });

  it("keeps the old name everywhere when the rename is refused", async () => {
    getTargetMock.mockResolvedValue(A);
    listMock.mockResolvedValue([A, B]);
    renameMock.mockRejectedValue(new Error("You don't have access to this target."));

    render(<TargetPageContent id="a" />);
    await screen.findByText("reviews for a");
    fireEvent.click(screen.getByRole("button", { name: "Rename this analysis" }));
    fireEvent.change(screen.getByLabelText("New name"), { target: { value: "Hijacked" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    await screen.findByText("You don't have access to this target.");
    expect(screen.getByRole("heading", { name: "Downtown lunch" })).toBeTruthy();
    expect(qaActiveTarget()).toContain("Downtown lunch");
  });
});
