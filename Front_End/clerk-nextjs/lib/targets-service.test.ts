import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  TargetValidationError,
  createTarget,
  getTarget,
  listReviews,
  listTargets,
  startIngestion,
} from "./targets-service";

const PLACE_ID = "0x89c25a2b1c1d3f3b:0x1a2b3c4d5e6f7a8b";
const GOOD_URL = `https://www.google.com/maps/place/Sample+Coffee/data=!4m7!3m6!1s${PLACE_ID}!8m2`;
const PROVIDER_FAILED = "Could not fetch reviews from the review provider. Please try again.";

// ---- helpers: a fake network, so no real server is needed --------------------

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const row = (overrides: Record<string, unknown> = {}) => ({
  id: "t1",
  business_name: "Sample Coffee",
  platform: "GOOGLE_MAPS",
  source_url: GOOD_URL,
  created_at: "2026-10-31T12:00:00Z",
  ...overrides,
});

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;
type Call = [string, RequestInit | undefined];

let fetchMock = vi.fn();

function routes(handler: Handler) {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => handler(url, init));
  vi.stubGlobal("fetch", fetchMock);
}

const calls = () => fetchMock.mock.calls as unknown as Call[];

function stubStorage(initial: Record<string, string> = {}) {
  const store = { ...initial };
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
  });
  return store;
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
});

// ---- createTarget ------------------------------------------------------------

describe("createTarget", () => {
  it("sends the trimmed name, the fixed platform and the trimmed link, then maps the saved row", async () => {
    routes(() => reply(row({ id: "t9" }), 201));

    const target = await createTarget({ name: "  Sample Coffee  ", sourceUrl: ` ${GOOD_URL} ` });

    const [url, init] = calls()[0];
    expect(url).toBe("/api/backend/targets");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      name: "Sample Coffee",
      platform: "GOOGLE_MAPS",
      sourceUrl: GOOD_URL,
    });
    expect(target.id).toBe("t9");
    expect(target.name).toBe("Sample Coffee");
    expect(target.platform).toBe("Google Maps");
    expect(target.ingestionStatus).toBe("not_started");
  });

  it("rejects invalid input without calling the server", async () => {
    routes(() => reply(row()));

    const err = await catchError(createTarget({ name: "", sourceUrl: "" }));

    expect(err).toBeInstanceOf(TargetValidationError);
    expect((err as TargetValidationError).fieldErrors.name).toBeDefined();
    expect(calls()).toHaveLength(0);
  });

  it("shows the server's message under the link field when the server rejects it", async () => {
    const message = "Enter the full Google Maps link for the place.";
    routes(() => reply({ detail: [{ loc: ["body", "sourceUrl"], msg: message }] }, 422));

    const err = await catchError(createTarget({ name: "Sample Coffee", sourceUrl: GOOD_URL }));

    expect(err).toBeInstanceOf(TargetValidationError);
    expect((err as TargetValidationError).fieldErrors.sourceUrl).toBe(message);
  });

  it("remembers the new target's id for the fallback list", async () => {
    const store = stubStorage();
    routes(() => reply(row({ id: "t9" }), 201));

    await createTarget({ name: "Sample Coffee", sourceUrl: GOOD_URL });

    expect(store["reviewlens:target-ids"]).toBe(JSON.stringify(["t9"]));
  });
});

// ---- error messages ----------------------------------------------------------

describe("error messages", () => {
  it.each([
    [401, { detail: "x" }, "Your session has expired. Please sign in again."],
    [403, { detail: "x" }, "You don't have access to this target."],
    [500, { detail: "database exploded" }, "The server ran into a problem. Please try again."],
    [502, { detail: PROVIDER_FAILED }, PROVIDER_FAILED],
    [400, { detail: "Bad request detail" }, "Bad request detail"],
    [400, {}, "Something went wrong. Please try again."],
  ])("turns a %i response into a readable message", async (status, body, message) => {
    routes(() => reply(body, status));

    const err = await catchError(listReviews("t1", 0));

    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe(message);
    expect((err as ApiError).status).toBe(status);
  });

  it("handles a plain-text server error without leaking it", async () => {
    routes(() => new Response("Internal Server Error", { status: 500 }));

    const err = await catchError(listReviews("t1", 0));

    expect(err.message).toBe("The server ran into a problem. Please try again.");
  });

  it("explains a network failure", async () => {
    routes(() => {
      throw new TypeError("Failed to fetch");
    });

    const err = await catchError(listReviews("t1", 0));

    expect(err.message).toBe("Could not reach the server. Check your connection and try again.");
  });
});

// ---- getTarget ---------------------------------------------------------------

describe("getTarget", () => {
  it("uses the ingestion state the backend reports, in a single request", async () => {
    routes(() => reply(row({ ingestion_status: "failed", ingestion_error: "Provider down" })));

    const target = await getTarget("t1");

    expect(target?.ingestionStatus).toBe("failed");
    expect(target?.ingestionMessage).toBe("Provider down");
    expect(calls()).toHaveLength(1);
  });

  it("maps the server's stored review count and average rating", async () => {
    routes(() => reply(row({
      ingestion_status: "completed",
      ingestion_skipped: 0,
      review_summary: { review_count: 3, average_rating: 4.25 },
    })));

    const target = await getTarget("t1");
    expect(target?.reviewSummary).toEqual({ count: 3, averageRating: 4.25 });
    expect(target?.skippedReviews).toBe(0);
  });

  it.each([[404], [403]])("returns null when the server answers %i", async (status) => {
    routes(() => reply({ detail: "nope" }, status));

    expect(await getTarget("t1")).toBeNull();
  });

  it("rethrows other failures", async () => {
    routes(() => reply({ detail: "boom" }, 500));

    const err = await catchError(getTarget("t1"));

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(500);
  });

  it("encodes the id in the address", async () => {
    routes(() => reply(row({ ingestion_status: "not_started" })));

    await getTarget("a b/c");

    expect(calls()[0][0]).toBe("/api/backend/targets/a%20b%2Fc");
  });

  it("does not infer a successful run from review rows when no job state is returned", async () => {
    routes((url) => (url.endsWith("/reviews") ? reply([{ id: "r1" }]) : reply(row())));

    expect((await getTarget("t1"))?.ingestionStatus).toBe("not_started");
    expect(calls()).toHaveLength(1);
  });
});

// ---- listTargets -------------------------------------------------------------

describe("listTargets", () => {
  it("maps the rows and lists the newest first", async () => {
    routes(() =>
      reply([
        row({ id: "old", business_name: "Old Place", created_at: "2026-10-01T00:00:00Z", ingestion_status: "completed" }),
        row({ id: "new", business_name: "New Place", created_at: "2026-10-30T00:00:00Z", ingestion_status: "failed" }),
      ])
    );

    const targets = await listTargets();

    expect(targets.map((t) => t.name)).toEqual(["New Place", "Old Place"]);
    expect(targets.map((t) => t.ingestionStatus)).toEqual(["failed", "completed"]);
  });

  it("falls back to remembered ids when the backend has no list endpoint, skipping missing ones", async () => {
    stubStorage({ "reviewlens:target-ids": JSON.stringify(["t1", "gone"]) });
    routes((url) => {
      if (url === "/api/backend/targets") return reply({ detail: "Method Not Allowed" }, 405);
      if (url.endsWith("/targets/t1")) return reply(row({ ingestion_status: "completed" }));
      return reply({ detail: "Target not found" }, 404);
    });

    const targets = await listTargets();

    expect(targets.map((t) => t.name)).toEqual(["Sample Coffee"]);
  });

  it("does not hide real failures behind the fallback", async () => {
    routes(() => reply({ detail: "boom" }, 500));

    const err = await catchError(listTargets());

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(500);
  });
});

// ---- startIngestion ----------------------------------------------------------

describe("startIngestion", () => {
  it("starts the job, then returns the refreshed target", async () => {
    routes((_url, init) =>
      init?.method === "POST" ? reply({ status: "completed" }) : reply(row({ ingestion_status: "completed" }))
    );

    const target = await startIngestion("t1");

    expect(calls()[0][0]).toBe("/api/backend/targets/t1/ingest");
    expect(calls()[0][1]?.method).toBe("POST");
    expect(target.ingestionStatus).toBe("completed");
  });

  it.each([[404], [405]])("explains it when the backend has no ingest endpoint (%i)", async (status) => {
    routes(() => reply({ detail: "nope" }, status));

    const err = await catchError(startIngestion("t1"));

    expect(err.message).toBe("Ingestion isn't available yet: the backend doesn't have an ingest endpoint.");
  });

  it("passes on the message when the review provider fails", async () => {
    routes(() => reply({ detail: PROVIDER_FAILED }, 502));

    const err = await catchError(startIngestion("t1"));

    expect(err.message).toBe(PROVIDER_FAILED);
  });

  it("reports a target that disappeared after the job ran", async () => {
    routes((_url, init) => (init?.method === "POST" ? reply({}) : reply({ detail: "Target not found" }, 404)));

    const err = await catchError(startIngestion("t1"));

    expect(err.message).toBe("This target no longer exists.");
  });
});

// ---- listReviews -------------------------------------------------------------

const reviewRows = (count: number) =>
  Array.from({ length: count }, (_, i) => ({
    id: `r${i}`,
    rating: 5,
    review_text: `text ${i}`,
    reviewed_at: "2026-10-31T00:00:00Z",
  }));

describe("listReviews", () => {
  it("asks for one extra row so it can tell whether another page exists", async () => {
    routes(() => reply([]));

    await listReviews("t1", 0);

    expect(calls()[0][0]).toBe("/api/backend/targets/t1/reviews?limit=6&offset=0");
  });

  it("shows 5 reviews and reports more when a sixth comes back", async () => {
    routes(() => reply(reviewRows(6)));

    const page = await listReviews("t1", 0);

    expect(page.reviews).toHaveLength(5);
    expect(page.reviews[4].id).toBe("r4");
    expect(page.hasMore).toBe(true);
  });

  it("reports no more when exactly 5 come back", async () => {
    routes(() => reply(reviewRows(5)));

    const page = await listReviews("t1", 0);

    expect(page.reviews).toHaveLength(5);
    expect(page.hasMore).toBe(false);
  });

  it("fills in empty text and a missing date", async () => {
    routes(() => reply([{ id: "r1", rating: 3, review_text: null, reviewed_at: null }]));

    const page = await listReviews("t1", 0);

    expect(page.reviews[0].text).toBe("");
    expect(page.reviews[0].date).toBeNull();
    expect(page.reviews[0].rating).toBe(3);
  });

  it("uses the offset and page size it is given", async () => {
    routes(() => reply([]));

    await listReviews("t1", 10, 2);

    expect(calls()[0][0]).toBe("/api/backend/targets/t1/reviews?limit=3&offset=10");
  });

  it("encodes the target id in the address", async () => {
    routes(() => reply([]));

    await listReviews("a b", 0);

    expect(calls()[0][0]).toBe("/api/backend/targets/a%20b/reviews?limit=6&offset=0");
  });
});
