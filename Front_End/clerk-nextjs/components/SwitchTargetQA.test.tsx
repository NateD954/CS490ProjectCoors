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
const fetchMock = vi.fn();
const PLACEHOLDER = "Ask a question about these reviews...";

// Target A has 3 reviews rated 5. Target B has 2 reviews rated 3.
const A: AnalysisTarget = {
  id: "a", name: "A's Gadgets", platform: "Google Maps", sourceUrl: "u", createdAt: "2026-10-31T12:00:00Z",
  ingestionStatus: "completed", reviewSummary: { count: 3, averageRating: 5 },
};
const B: AnalysisTarget = {
  id: "b", name: "B's Repair Shop", platform: "Google Maps", sourceUrl: "u", createdAt: "2026-10-31T12:00:00Z",
  ingestionStatus: "completed", reviewSummary: { count: 2, averageRating: 3 },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function askQuestion(question: string) {
  fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await screen.findByText("An answer.");
}

// S2-018: after switching targets, questions and the summary belong to the new target.
describe("Switching from target A to target B", () => {
  it("sends the next question to B and not A, and clears A's answer", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ answer: "An answer." }) });
    getTargetMock.mockImplementation(async (id) => (id === "a" ? A : B));
    listMock.mockResolvedValue([A, B]);

    const view = render(<TargetPageContent id="a" />);
    await screen.findByText("Stored reviews");
    await askQuestion("What about A?");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/targets/a/ask");

    view.rerender(<TargetPageContent id="b" />);
    await screen.findByText("reviews for b");

    expect(screen.queryByText("An answer.")).toBeNull(); // A's answer is gone
    await askQuestion("What about B?");
    const [url, init] = fetchMock.mock.calls[1];
    expect(String(url)).toContain("/targets/b/ask");
    expect(String(url)).not.toContain("/targets/a/");
    expect(JSON.parse(init.body)).toEqual({ question: "What about B?" });
  });

  it("shows B's summary and name, not A's", async () => {
    getTargetMock.mockImplementation(async (id) => (id === "a" ? A : B));
    listMock.mockResolvedValue([A, B]);

    const view = render(<TargetPageContent id="a" />);
    expect((await screen.findByText("Stored reviews")).nextElementSibling?.textContent).toBe("3");
    expect(screen.getByText("Average rating").nextElementSibling?.textContent).toBe("5.00 / 5");

    view.rerender(<TargetPageContent id="b" />);
    await screen.findByText("reviews for b");

    expect(screen.getByText("Stored reviews").nextElementSibling?.textContent).toBe("2");
    expect(screen.getByText("Average rating").nextElementSibling?.textContent).toBe("3.00 / 5");
    expect(screen.getAllByText("B's Repair Shop", { selector: "span" })).toHaveLength(2);
    expect(screen.queryByText("A's Gadgets", { selector: "span" })).toBeNull();
  });
});
