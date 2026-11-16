import { describe, expect, it, vi } from "vitest";

// Stand-ins for Clerk: the middleware just hands back the function it was given, and
// the route matcher turns each pattern into a regular expression on the path.
vi.mock("@clerk/nextjs/server", () => ({
  clerkMiddleware: (handler: unknown) => handler,
  createRouteMatcher: (patterns: string[]) => (req: { url: string }) =>
    patterns.some((pattern) => new RegExp(`^${pattern}$`).test(new URL(req.url).pathname)),
}));

import middleware, { config } from "./proxy";

const run = middleware as unknown as (auth: unknown, req: { url: string }) => Promise<void>;

function makeAuth() {
  return Object.assign(vi.fn(), { protect: vi.fn() });
}

async function visit(path: string) {
  const auth = makeAuth();
  await run(auth, { url: `http://localhost:3000${path}` });
  return auth;
}

describe("route protection", () => {
  it.each(["/home", "/home/anything"])("sends signed-out visitors away from %s", async (path) => {
    const auth = await visit(path);

    expect(auth.protect).toHaveBeenCalledTimes(1);
  });

  it("protects target workspaces too, so a direct link needs a login", async () => {
    const auth = await visit("/targets/some-target-id");

    expect(auth.protect).toHaveBeenCalledTimes(1);
  });

  it.each(["/", "/sign-in", "/about"])("leaves %s open to everyone", async (path) => {
    const auth = await visit(path);

    expect(auth.protect).not.toHaveBeenCalled();
  });
});

describe("which requests the middleware runs on", () => {
  const runsOn = (path: string) => config.matcher.some((pattern) => new RegExp(`^${pattern}$`).test(path));

  it.each(["/", "/home", "/targets/abc", "/data.json"])("runs on page route %s", (path) => {
    expect(runsOn(path)).toBe(true);
  });

  it.each(["/api/backend/targets", "/api/anything", "/trpc/anything"])("always runs on %s", (path) => {
    expect(runsOn(path)).toBe(true);
  });

  it.each(["/_next/static/chunk.js", "/logo.png", "/styles/site.css", "/favicon.ico"])(
    "skips static file %s",
    (path) => {
      expect(runsOn(path)).toBe(false);
    }
  );
});
