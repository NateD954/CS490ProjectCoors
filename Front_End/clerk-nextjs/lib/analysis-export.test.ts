// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, downloadAnalysisMarkdown, markdownFileName } from "./targets-service";

const reply = (body: BodyInit | null, status = 200, type = "text/markdown") =>
  new Response(body, { status, headers: { "Content-Type": type } });

let fetchMock = vi.fn();
function routes(outcome: () => Response | Promise<Response>) {
  fetchMock = vi.fn(async () => outcome());
  vi.stubGlobal("fetch", fetchMock);
}

// jsdom cannot really save a file, so these stand-ins record what would have been saved.
const original = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
function stubDownloads() {
  const saved: { href: string; name: string }[] = [];
  const revoke = vi.fn();
  Object.assign(URL, { createObjectURL: vi.fn(() => "blob:analysis"), revokeObjectURL: revoke });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    saved.push({ href: this.href, name: this.download });
  });
  return { saved, revoke };
}

async function catchError(promise: Promise<unknown>): Promise<Error> {
  try {
    await promise;
  } catch (err) {
    return err as Error;
  }
  throw new Error("Expected the call to fail, but it succeeded.");
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Object.assign(URL, { createObjectURL: original.create, revokeObjectURL: original.revoke });
});

describe("downloadAnalysisMarkdown", () => {
  it("asks the backend for the analysis export and saves it as a named .md file", async () => {
    routes(() => reply("# ReviewLens analysis: Sample Cafe\n"));
    const { saved, revoke } = stubDownloads();

    await downloadAnalysisMarkdown({ id: "a b", name: "Sample Cafe" });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/backend/targets/a%20b/export/markdown");
    expect(saved).toHaveLength(1);
    expect(saved[0].href).toBe("blob:analysis");
    expect(saved[0].name).toMatch(/^reviewlens-sample-cafe-analysis-\d{4}-\d{2}-\d{2}\.md$/);
    expect(revoke).toHaveBeenCalledWith("blob:analysis");
    expect(document.querySelector("a[download]")).toBeNull(); // the temporary link is removed
  });

  it.each([
    [401, "Your session has expired. Please sign in again."],
    [403, "You don't have access to this target."],
    [500, "The server ran into a problem. Please try again."],
  ])("turns a %i answer into a readable message and saves nothing", async (status, message) => {
    routes(() => reply(JSON.stringify({ detail: "x" }), status, "application/json"));
    const { saved } = stubDownloads();

    const err = await catchError(downloadAnalysisMarkdown({ id: "t1", name: "Cafe" }));

    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe(message);
    expect(saved).toHaveLength(0);
  });

  it("explains a network failure", async () => {
    routes(() => {
      throw new TypeError("Failed to fetch");
    });
    const { saved } = stubDownloads();

    const err = await catchError(downloadAnalysisMarkdown({ id: "t1", name: "Cafe" }));

    expect(err.message).toBe("Could not reach the server. Check your connection and try again.");
    expect(saved).toHaveLength(0);
  });
});

describe("markdownFileName", () => {
  const day = new Date("2026-11-26T12:00:00Z");

  it("builds a safe file name from the target name and the date", () => {
    expect(markdownFileName("Joe's Pizza & Pasta!", day)).toBe("reviewlens-joe-s-pizza-pasta-analysis-2026-11-26.md");
  });

  it("falls back to a plain word when the name has no letters or digits", () => {
    expect(markdownFileName("***", day)).toBe("reviewlens-target-analysis-2026-11-26.md");
  });

  it("uses today's date by default", () => {
    expect(markdownFileName("Cafe")).toMatch(/^reviewlens-cafe-analysis-\d{4}-\d{2}-\d{2}\.md$/);
  });
});
