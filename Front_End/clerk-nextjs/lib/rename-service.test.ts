import { afterEach, describe, expect, it, vi } from "vitest";
import { renameTarget, RenameError } from "./rename-service";
import { validateName } from "./name-rules";

const fetchMock = vi.fn();

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
}

async function messageOf(promise: Promise<unknown>) {
  try {
    await promise;
  } catch (err) {
    expect(err).toBeInstanceOf(RenameError);
    return (err as Error).message;
  }
  throw new Error("expected renameTarget to fail");
}

// S3-002: renaming sends only the name and reports problems in plain words.
describe("renameTarget", () => {
  it("sends only the trimmed name to the target's address and returns the saved name", async () => {
    reply(200, { id: "t1", business_name: "Lunch spot downtown" });

    const saved = await renameTarget("t1", "  Lunch spot downtown ");

    expect(saved).toBe("Lunch spot downtown");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/backend/targets/t1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ name: "Lunch spot downtown" }); // nothing else is sent
  });

  it("makes no request for a name that is clearly unusable", async () => {
    vi.stubGlobal("fetch", fetchMock);

    expect(await messageOf(renameTarget("t1", "   "))).toBe("Enter a name for this analysis.");
    expect(await messageOf(renameTarget("t1", "---"))).toBe("Use at least one letter or number in the name.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server's message when it rejects the name", async () => {
    reply(422, { detail: [{ loc: ["body", "name"], msg: "Keep the name under 120 characters." }] });

    expect(await messageOf(renameTarget("t1", "A fine name"))).toBe("Keep the name under 120 characters.");
  });

  it.each([
    [401, "Your session has expired. Please sign in again."],
    [403, "You don't have access to this target."],
    [404, "This target was not found. It may have been removed."],
    [500, "The server ran into a problem. Please try again."],
    [418, "Could not rename this target. Please try again."],
  ])("explains a %i answer", async (status, message) => {
    reply(status, { detail: "internal detail that users should not see" });

    expect(await messageOf(renameTarget("t1", "A fine name"))).toBe(message);
  });

  it("says so when the server cannot be reached", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));
    vi.stubGlobal("fetch", fetchMock);

    expect(await messageOf(renameTarget("t1", "A fine name"))).toBe("Could not reach the server. Check your connection and try again.");
  });

  it("puts the id in the address safely", async () => {
    reply(200, { business_name: "x" });

    await renameTarget("a/b?c", "Name");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/backend/targets/a%2Fb%3Fc");
  });
});

describe("validateName", () => {
  it("accepts ordinary names, other alphabets and numbers", () => {
    for (const ok of ["Chipotle", "カフェ 2", "7", "  spaced   out  "]) expect(validateName(ok)).toBeUndefined();
  });

  it("rejects empty, too long and symbol-only names", () => {
    expect(validateName("")).toBeTruthy();
    expect(validateName("x".repeat(121))).toBeTruthy();
    expect(validateName("!!! ...")).toBeTruthy();
    expect(validateName("x".repeat(120))).toBeUndefined();
  });
});
