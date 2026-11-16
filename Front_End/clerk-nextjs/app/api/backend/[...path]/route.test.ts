import { afterEach, describe, expect, it, vi } from "vitest";
import { auth } from "@clerk/nextjs/server";

// BACKEND_URL is read when the route file loads, so set it before the import below.
vi.hoisted(() => {
  process.env.BACKEND_URL = "http://backend.test";
});

vi.mock("@clerk/nextjs/server", () => ({ auth: vi.fn() }));

import { DELETE, GET, PATCH, POST, PUT } from "./route";

const authMock = vi.mocked(auth);
let fetchMock = vi.fn();

function signedInAs(token: string | null = "test-token") {
  authMock.mockResolvedValue({ userId: "user_1", getToken: async () => token } as never);
}

function signedOut() {
  authMock.mockResolvedValue({ userId: null, getToken: async () => null } as never);
}

function backendAnswers(outcome: Response | Error) {
  fetchMock = vi.fn(async () => {
    if (outcome instanceof Error) throw outcome;
    return outcome;
  });
  vi.stubGlobal("fetch", fetchMock);
}

const jsonReply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const context = (...path: string[]) => ({ params: Promise.resolve({ path }) });
const browserRequest = (path: string, init?: RequestInit) => new Request(`http://localhost:3000/api/backend/${path}`, init);

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("backend pass-through route: who may use it", () => {
  it("refuses a visitor who is not signed in and never contacts the backend", async () => {
    signedOut();
    backendAnswers(jsonReply({}));

    const res = await GET(browserRequest("targets"), context("targets"));

    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ detail: "You are not signed in." });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses a user whose session gives no token and never contacts the backend", async () => {
    signedInAs(null);
    backendAnswers(jsonReply({}));

    const res = await GET(browserRequest("targets"), context("targets"));

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("backend pass-through route: forwarding", () => {
  it("sends a read to the backend with the user's token and returns the answer", async () => {
    signedInAs("abc123");
    backendAnswers(jsonReply([{ id: "r1" }]));

    const res = await GET(browserRequest("targets/t1/reviews?limit=6&offset=0"), context("targets", "t1", "reviews"));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/targets/t1/reviews?limit=6&offset=0");
    expect(init.method).toBe("GET");
    expect(init.headers.Authorization).toBe("Bearer abc123");
    expect(init.headers["Content-Type"]).toBeUndefined(); // a read has no body to describe
    expect(init.body).toBeUndefined();
    expect(init.cache).toBe("no-store");
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual([{ id: "r1" }]);
    expect(res.headers.get("Content-Type")).toBe("application/json");
  });

  it("passes on the body of a write and says it is JSON", async () => {
    signedInAs();
    backendAnswers(jsonReply({ id: "t9" }, 201));

    const res = await POST(
      browserRequest("targets", { method: "POST", body: JSON.stringify({ name: "Cafe" }) }),
      context("targets")
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/targets");
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"name":"Cafe"}');
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(res.status).toBe(201);
  });

  it.each([
    ["PUT", PUT],
    ["PATCH", PATCH],
    ["DELETE", DELETE],
  ])("forwards %s requests with their own method", async (method, handler) => {
    signedInAs();
    backendAnswers(jsonReply({ ok: true }));

    await handler(browserRequest("targets/t1", { method }), context("targets", "t1"));

    expect(fetchMock.mock.calls[0][1].method).toBe(method);
  });

  it("encodes each part of the path so it cannot reach a different address", async () => {
    signedInAs();
    backendAnswers(jsonReply({}));

    await GET(browserRequest("targets/a%20b%2Fc"), context("targets", "a b/c"));

    expect(fetchMock.mock.calls[0][0]).toBe("http://backend.test/api/targets/a%20b%2Fc");
  });

  it("passes the backend's error status and message straight through", async () => {
    signedInAs();
    backendAnswers(jsonReply({ detail: "Access forbidden" }, 403));

    const res = await GET(browserRequest("targets/t1"), context("targets", "t1"));

    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({ detail: "Access forbidden" });
  });

  it("treats an answer with no content type as JSON", async () => {
    signedInAs();
    backendAnswers(new Response(null, { status: 204 }));

    const res = await DELETE(browserRequest("targets/t1", { method: "DELETE" }), context("targets", "t1"));

    expect(res.status).toBe(204);
    expect(res.headers.get("Content-Type")).toBe("application/json");
  });

  it("says the backend could not be reached when the connection fails", async () => {
    signedInAs();
    backendAnswers(new TypeError("fetch failed"));

    const res = await GET(browserRequest("targets"), context("targets"));

    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ detail: "The backend server could not be reached." });
  });
});

describe("backend pass-through route: settings", () => {
  it("uses the local backend when BACKEND_URL is not set", async () => {
    const previous = process.env.BACKEND_URL;
    try {
      vi.resetModules();
      delete process.env.BACKEND_URL;
      const { auth: freshAuth } = await import("@clerk/nextjs/server");
      vi.mocked(freshAuth).mockResolvedValue({ userId: "user_1", getToken: async () => "tok" } as never);
      const fresh = await import("./route");
      backendAnswers(jsonReply([]));

      await fresh.GET(browserRequest("targets"), context("targets"));

      expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/api/targets");
    } finally {
      process.env.BACKEND_URL = previous;
    }
  });
});
