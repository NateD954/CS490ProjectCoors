import { afterEach, describe, expect, it, vi } from "vitest";
import { saveTargetAs, suggestCopyName, SaveAsError } from "./save-as-service";

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
    expect(err).toBeInstanceOf(SaveAsError);
    return (err as Error).message;
  }
  throw new Error("expected saveTargetAs to fail");
}

// S3-003: Save As sends only the new name and reports problems in plain words.
describe("saveTargetAs", () => {
  it("posts the trimmed name to the save-as address and returns the new analysis", async () => {
    reply(201, { id: "copy-1", business_name: "Lunch copy" });

    const saved = await saveTargetAs("t1", "  Lunch copy ");

    expect(saved).toEqual({ id: "copy-1", name: "Lunch copy" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/backend/targets/t1/save-as");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ name: "Lunch copy" }); // nothing else is sent
  });

  it("makes no request for a name that is clearly unusable", async () => {
    vi.stubGlobal("fetch", fetchMock);

    expect(await messageOf(saveTargetAs("t1", "   "))).toBe("Enter a name for this analysis.");
    expect(await messageOf(saveTargetAs("t1", "---"))).toBe("Use at least one letter or number in the name.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server's message when it rejects the name", async () => {
    reply(422, { detail: [{ loc: ["body", "name"], msg: "Keep the name under 120 characters." }] });

    expect(await messageOf(saveTargetAs("t1", "A fine name"))).toBe("Keep the name under 120 characters.");
  });

  it.each([
    [401, "Your session has expired. Please sign in again."],
    [403, "You don't have access to this target."],
    [404, "This target was not found. It may have been removed."],
    [503, "Could not save the copy. Nothing was changed. Please try again."],
    [418, "Could not save the copy. Please try again."],
  ])("explains a %i reply in plain words", async (status, message) => {
    reply(status, { detail: "internal details that must not be shown" });

    expect(await messageOf(saveTargetAs("t1", "A fine name"))).toBe(message);
  });

  it("explains a lost connection", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    expect(await messageOf(saveTargetAs("t1", "A fine name"))).toBe("Could not reach the server. Check your connection and try again.");
  });

  it("does not accept a success reply that has no new id", async () => {
    reply(201, {});

    expect(await messageOf(saveTargetAs("t1", "A fine name"))).toBe("Could not save the copy. Please try again.");
  });

  it("encodes the id in the address", async () => {
    reply(201, { id: "c" });

    await saveTargetAs("a/b", "Name");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/backend/targets/a%2Fb/save-as");
  });
});

describe("suggestCopyName", () => {
  it("adds (copy) to the name", () => {
    expect(suggestCopyName("Downtown lunch")).toBe("Downtown lunch (copy)");
  });

  it("tidies spaces first", () => {
    expect(suggestCopyName("  Downtown   lunch ")).toBe("Downtown lunch (copy)");
  });

  it("stays within the name length limit", () => {
    expect(suggestCopyName("x".repeat(200)).length).toBeLessThanOrEqual(120);
    expect(suggestCopyName("x".repeat(200)).endsWith(" (copy)")).toBe(true);
  });
});
