// Server-side pass-through to the FastAPI backend.
//   Browser  ->  /api/backend/targets  ->  (this file)  ->  BACKEND_URL/api/targets
// It attaches the signed-in user's Clerk token, which the backend's
// getCurrentUserId() verifies. Because the browser only talks to this same-origin
// route, the backend's CORS settings never come into play.
import { auth } from "@clerk/nextjs/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function forward(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { userId, getToken } = await auth();
  const token = await getToken();
  if (!userId || !token) {
    return Response.json({ detail: "You are not signed in." }, { status: 401 });
  }

  const { path } = await ctx.params;
  const search = new URL(req.url).search;
  const target = `${BACKEND_URL}/api/${path.map(encodeURIComponent).join("/")}${search}`;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(hasBody ? { "Content-Type": "application/json" } : {}),
      },
      body: hasBody ? await req.text() : undefined,
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "The backend server could not be reached." }, { status: 502 });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
