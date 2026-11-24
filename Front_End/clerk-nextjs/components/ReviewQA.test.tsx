// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import ReviewQA from "./ReviewQA";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => "test-token" }),
}));

const fetchMock = vi.fn();

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function setup() {
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<ReviewQA targetId="t1" />);
  const input = screen.getByPlaceholderText("Ask a question about these reviews...") as HTMLInputElement;
  return { ...view, input };
}

function ask(input: HTMLInputElement, question: string) {
  fireEvent.change(input, { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

describe("ReviewQA", () => {
  it("keeps the Ask button disabled until a question is typed", () => {
    const { input } = setup();
    const button = screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement;

    expect(button.disabled).toBe(true);
    fireEvent.change(input, { target: { value: "What do people like?" } });
    expect(button.disabled).toBe(false);
  });

  it("sends the question with the user's token and shows the answer", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).endsWith("/history")) {
        return { ok: true, json: async () => [] };
      }
      return { ok: true, json: async () => ({ answer: "Customers love the tacos." }) };
    });
    const { input } = setup();

    ask(input, "What do people like?");

    expect(await screen.findByText("Customers love the tacos.")).toBeTruthy();
    const askCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/targets/t1/ask"))!;
    expect(askCall).toBeTruthy();
    const [url, init] = askCall;
    expect(String(url)).toContain("/targets/t1/ask");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer test-token");
    expect(JSON.parse(init.body)).toEqual({ question: "What do people like?" });
  });

  it("restores persisted Q&A history when reopening a target", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).endsWith("/history")) {
        return {
          ok: true,
          json: async () => [
            { id: "m1", question: "How is parking?", answer: "Free lot behind the building." },
          ],
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    setup();

    expect(await screen.findByText("Q: How is parking?")).toBeTruthy();
    expect(await screen.findByText("Free lot behind the building.")).toBeTruthy();
  });

  it("shows Thinking... and disables the input while waiting for the answer", async () => {
    let finish!: (value: unknown) => void;
    fetchMock.mockImplementation((url: string) => {
      if (String(url).endsWith("/history")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      return new Promise((resolve) => (finish = resolve));
    });
    const { input } = setup();

    ask(input, "What do people like?");

    const waiting = (await screen.findByRole("button", { name: "Thinking..." })) as HTMLButtonElement;
    expect(waiting.disabled).toBe(true);
    expect(input.disabled).toBe(true);

    finish({ ok: true, json: async () => ({ answer: "Done." }) });
    expect(await screen.findByText("Done.")).toBeTruthy();
  });

  it("does not send anything when the question is only spaces", () => {
    const { container, input } = setup();
    fireEvent.change(input, { target: { value: "   " } });

    fireEvent.submit(container.querySelector("form")!);

    const askCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes("/ask"));
    expect(askCalls).toHaveLength(0);
  });

  it("shows a friendly message when the server answers with an error", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).endsWith("/history")) {
        return { ok: true, json: async () => [] };
      }
      return { ok: false, json: async () => ({}) };
    });
    const { input } = setup();

    ask(input, "What do people like?");

    expect(await screen.findByText("Failed to get an answer. Please try again.")).toBeTruthy();
  });

  it("shows the message when the request itself fails", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).endsWith("/history")) {
        return { ok: true, json: async () => [] };
      }
      throw new Error("Network down");
    });
    const { input } = setup();

    ask(input, "What do people like?");

    expect(await screen.findByText("Network down")).toBeTruthy();
  });

  it("shows text when the failure is not an Error object", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).endsWith("/history")) {
        return { ok: true, json: async () => [] };
      }
      throw "plain text failure";
    });
    const { input } = setup();

    ask(input, "What do people like?");

    expect(await screen.findByText("plain text failure")).toBeTruthy();
  });
});