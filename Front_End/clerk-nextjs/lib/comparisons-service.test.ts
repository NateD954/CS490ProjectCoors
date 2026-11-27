import { afterEach, describe, expect, it, vi } from "vitest";
import { createComparison, deleteComparison, getComparison, listComparisons } from "./comparisons-service";

const saved = { id: "c1", name: "A vs B", target_a_id: "a", target_b_id: "b", created_at: "2026-11-26T00:00:00Z" };
const fetchMock = vi.fn();

function reply(body: unknown, status = 200) {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValue(new Response(status === 204 ? null : JSON.stringify(body), { status }));
}

afterEach(() => { vi.unstubAllGlobals(); vi.resetAllMocks(); });

describe("comparison requests", () => {
  it("loads persisted comparisons through the authenticated proxy without caching", async () => {
    reply([saved]);
    expect(await listComparisons()).toEqual([saved]);
    expect(fetchMock).toHaveBeenCalledWith("/api/backend/comparisons", expect.objectContaining({ cache: "no-store" }));
  });

  it("reopens the selected comparison with a safely encoded id", async () => {
    reply(saved);
    expect(await getComparison("a/b")).toEqual(saved);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/backend/comparisons/a%2Fb");
  });

  it("saves a trimmed name and both ids, without accepting an owner", async () => {
    reply(saved, 201);
    expect(await createComparison({ name: "  A vs B  ", targetAId: "a", targetBId: "b" })).toEqual(saved);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "A vs B", targetAId: "a", targetBId: "b" }),
    });
  });

  it("deletes only the comparison and accepts an empty 204 response", async () => {
    reply(null, 204);
    expect(await deleteComparison("a/b")).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith("/api/backend/comparisons/a%2Fb", expect.objectContaining({ method: "DELETE" }));
  });

  it.each([
    [400, "Choose two different targets to compare.", "Choose two different targets to compare."],
    [404, "Comparison not found.", "Comparison not found."],
    [401, "Private", "Your session has expired. Please sign in again."],
    [403, "Private", "You don't have access to this comparison or its targets."],
    [500, "Private", "Could not load or save the comparison. Please try again."],
    [422, [{ msg: "Invalid" }], "The comparison request failed. Please try again."],
  ])("shows a readable message for HTTP %s", async (status, detail, message) => {
    reply({ detail }, status as number);
    await expect(listComparisons()).rejects.toThrow(message as string);
  });

  it("handles an error response that is not JSON", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(new Response("Bad gateway", { status: 502 }));
    await expect(listComparisons()).rejects.toThrow("Could not load or save the comparison.");
  });

  it("handles a failed connection", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockRejectedValue(new TypeError("Connection failed"));
    await expect(listComparisons()).rejects.toThrow("Could not reach the server.");
  });
});
