// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AnalysisTarget } from "@/lib/types";
import { getTarget, listTargets } from "@/lib/targets-service";
import { TargetPageContent } from "./TargetPageContent";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("./ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), loading: vi.fn(() => "x"), dismiss: vi.fn() }),
}));
vi.mock("@clerk/nextjs", () => ({ useAuth: () => ({ getToken: async () => "tok" }) }));
vi.mock("@/lib/targets-service", () => ({ getTarget: vi.fn(), listTargets: vi.fn(), startIngestion: vi.fn() }));
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

function t(id: string, name: string): AnalysisTarget {
  return { id, name, platform: "Google Maps", sourceUrl: "u", createdAt: "2026-10-31T12:00:00Z", ingestionStatus: "not_started" };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// S2-017 tests for TargetPageContent: same name everywhere, and nothing stale after a switch.
describe("Active target is shown consistently (S2-017)", () => {
  it("shows the same target name in the switcher, workspace summary and Q&A", async () => {
    getTargetMock.mockResolvedValue(t("a", "Coffee A"));
    listMock.mockResolvedValue([t("a", "Coffee A"), t("b", "Pizza B")]);

    render(<TargetPageContent id="a" />);

    // Workspace summary and Q&A each print "Active target: <name>".
    expect(await screen.findAllByText("Coffee A", { selector: "span" })).toHaveLength(2);
    expect((screen.getByLabelText("Active target") as HTMLSelectElement).value).toBe("a");
    expect(screen.queryByText("Pizza B", { selector: "span" })).toBeNull();
  });

  it("moves everything to the new target and clears the old question and answer", async () => {
    getTargetMock.mockImplementation(async (id) => (id === "a" ? t("a", "Coffee A") : t("b", "Pizza B")));
    listMock.mockResolvedValue([t("a", "Coffee A"), t("b", "Pizza B")]);

    const view = render(<TargetPageContent id="a" />);
    await screen.findAllByText("Coffee A", { selector: "span" });
    const input = screen.getByPlaceholderText("Ask a question about these reviews...") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "old question about A" } });

    view.rerender(<TargetPageContent id="b" />);

    expect(await screen.findAllByText("Pizza B", { selector: "span" })).toHaveLength(2);
    expect(screen.queryByText("Coffee A", { selector: "span" })).toBeNull();
    expect(screen.getByText("reviews for b")).toBeTruthy();
    expect((screen.getByPlaceholderText("Ask a question about these reviews...") as HTMLInputElement).value).toBe("");
  });
});
