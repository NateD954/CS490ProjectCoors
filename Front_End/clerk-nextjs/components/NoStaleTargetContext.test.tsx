// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
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
const fetchMock = vi.fn();
const PLACEHOLDER = "Ask a question about these reviews...";

function target(id: string, name: string): AnalysisTarget {
  return {
    id, name, platform: "Google Maps", sourceUrl: "u", createdAt: "2026-10-31T12:00:00Z",
    ingestionStatus: "completed", reviewSummary: { count: 3, averageRating: 4 },
  };
}
const A = target("a", "A's Gadgets");
const B = target("b", "B's Repair Shop");

// A promise the test resolves by hand, to control which response arrives first.
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

// The Active target line inside the Q&A box (the other one is in the workspace summary).
function qaActiveTarget() {
  return screen.getByText("Ask ReviewLens AI").parentElement!.textContent ?? "";
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

// S2-019: moving from one target to another must not keep anything from the old one.
describe("No stale context after switching targets", () => {
  it("does not show target A's name over B's Q&A while B is still loading", async () => {
    const bLoad = deferred<AnalysisTarget | null>();
    getTargetMock.mockImplementation((id) => (id === "a" ? Promise.resolve(A) : bLoad.promise));
    listMock.mockResolvedValue([A, B]);

    const view = render(<TargetPageContent id="a" />);
    await screen.findByText("reviews for a");
    expect(qaActiveTarget()).toContain("A's Gadgets");

    view.rerender(<TargetPageContent id="b" />);

    expect(qaActiveTarget()).not.toContain("A's Gadgets");
    await act(async () => bLoad.resolve(B));
    expect(qaActiveTarget()).toContain("B's Repair Shop");
  });

  it("ignores a slow response for A that arrives after switching to B", async () => {
    const aLoad = deferred<AnalysisTarget | null>();
    getTargetMock.mockImplementation((id) => (id === "a" ? aLoad.promise : Promise.resolve(B)));
    listMock.mockResolvedValue([A, B]);

    const view = render(<TargetPageContent id="a" />);
    view.rerender(<TargetPageContent id="b" />);
    await screen.findByText("reviews for b");

    await act(async () => aLoad.resolve(A)); // A's response arrives late

    expect(qaActiveTarget()).toContain("B's Repair Shop");
    expect(qaActiveTarget()).not.toContain("A's Gadgets");
  });

  it("does not show A's slow answer under B", async () => {
    const answerForA = deferred<unknown>();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReturnValueOnce(answerForA.promise);
    getTargetMock.mockImplementation(async (id) => (id === "a" ? A : B));
    listMock.mockResolvedValue([A, B]);

    const view = render(<TargetPageContent id="a" />);
    await screen.findByText("reviews for a");
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "What about A?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    view.rerender(<TargetPageContent id="b" />);
    await screen.findByText("reviews for b");
    await act(async () => answerForA.resolve({ ok: true, json: async () => ({ answer: "Answer about A only." }) }));

    expect(screen.queryByText("Answer about A only.")).toBeNull();
    expect((screen.getByPlaceholderText(PLACEHOLDER) as HTMLInputElement).value).toBe("");
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).textContent).toBe("Ask"); // not stuck on "Thinking..."
  });

  it("goes A, then B, then A again and shows only the active target each time", async () => {
    getTargetMock.mockImplementation(async (id) => (id === "a" ? A : B));
    listMock.mockResolvedValue([A, B]);

    const view = render(<TargetPageContent id="a" />);
    await screen.findByText("reviews for a");
    view.rerender(<TargetPageContent id="b" />);
    await screen.findByText("reviews for b");
    view.rerender(<TargetPageContent id="a" />);
    await screen.findByText("reviews for a");

    expect(qaActiveTarget()).toContain("A's Gadgets");
    expect(qaActiveTarget()).not.toContain("B's Repair Shop");
    expect(screen.queryByText("reviews for b")).toBeNull();
  });
});
