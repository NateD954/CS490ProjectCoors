// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, csvFileName, downloadReviewsCsv } from "./targets-service";

const CSV = "source_review_id,rating\r\nr1,5\r\n";

const reply = (body: BodyInit | null, status = 200, type = "text/csv") =>
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
  Object.assign(URL, { createObjectURL: vi.fn(() => "blob:reviews"), revokeObjectURL: revoke });
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

describe("downloadReviewsCsv", () => {
  it("asks the backend for the target's export and saves it as a named CSV file", async () => {
    routes(() => reply(CSV));
    const { saved, revoke } = stubDownloads();

    await downloadReviewsCsv({ id: "a b", name: "Sample Cafe" });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/backend/targets/a%20b/reviews/export");
    expect(saved).toHaveLength(1);
    expect(saved[0].href).toBe("blob:reviews");
    expect(saved[0].name).toMatch(/^reviewlens-sample-cafe-reviews-\d{4}-\d{2}-\d{2}\.csv$/);
    expect(revoke).toHaveBeenCalledWith("blob:reviews");
    expect(document.querySelector("a[download]")).toBeNull(); // the temporary link is removed
  });

  it.each([
    [401, "Your session has expired. Please sign in again."],
    [403, "You don't have access to this target."],
    [500, "The server ran into a problem. Please try again."],
  ])("turns a %i answer into a readable message and saves nothing", async (status, message) => {
    routes(() => reply(JSON.stringify({ detail: "x" }), status, "application/json"));
    const { saved } = stubDownloads();

    const err = await catchError(downloadReviewsCsv({ id: "t1", name: "Cafe" }));

    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe(message);
    expect(saved).toHaveLength(0);
  });

  it("explains a network failure", async () => {
    routes(() => {
      throw new TypeError("Failed to fetch");
    });
    const { saved } = stubDownloads();

    const err = await catchError(downloadReviewsCsv({ id: "t1", name: "Cafe" }));

    expect(err.message).toBe("Could not reach the server. Check your connection and try again.");
    expect(saved).toHaveLength(0);
  });
});

describe("csvFileName", () => {
  const day = new Date("2026-11-24T12:00:00Z");

  it("builds a safe file name from the target name and the date", () => {
    expect(csvFileName("Joe's Pizza & Pasta!", day)).toBe("reviewlens-joe-s-pizza-pasta-reviews-2026-11-24.csv");
  });

  it("turns accents and dashes in the name into a clean, readable file name", () => {
    expect(csvFileName("Café Blue Bottle — Mint Plaza", day)).toBe("reviewlens-cafe-blue-bottle-mint-plaza-reviews-2026-11-24.csv");
  });

  it("falls back to a plain word when the name has no letters or digits", () => {
    expect(csvFileName("***", day)).toBe("reviewlens-target-reviews-2026-11-24.csv");
  });

  it("uses today's date by default", () => {
    expect(csvFileName("Cafe")).toMatch(/^reviewlens-cafe-reviews-\d{4}-\d{2}-\d{2}\.csv$/);
  });
});
