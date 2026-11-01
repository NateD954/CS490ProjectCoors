// ---------------------------------------------------------------------------
// SERVICE BOUNDARY for AnalysisTarget, connected to the FastAPI backend
// (Back_End/app/main.py) through the pass-through route at
// app/api/backend/[...path]/route.ts. Components only call the four exported
// functions, so they don't know or care how the data is fetched.
//
// Backend endpoints used today:
//   POST /api/targets                 create (works as soon as the DB columns line up)
//   GET  /api/targets/{id}            fetch one (owner only)
//   GET  /api/targets/{id}/reviews    used to tell whether ingestion has produced data
// Also used (the UI copes if an older backend lacks them):
//   GET  /api/targets                 list the signed-in user's targets
//   POST /api/targets/{id}/ingest     run the scraper for a target
// ---------------------------------------------------------------------------
import { PLATFORM_LABELS, TEAM_PLATFORM } from "./config";
import type { AnalysisTarget, IngestionStatus, NewTargetInput } from "./types";
import { hasErrors, validateTargetInput, type FieldErrors } from "./validation";

const BASE = "/api/backend";

export class TargetValidationError extends Error {
  fieldErrors: FieldErrors;
  constructor(fieldErrors: FieldErrors) {
    super("Some fields are invalid.");
    this.name = "TargetValidationError";
    this.fieldErrors = fieldErrors;
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// ----- HTTP helpers --------------------------------------------------------

async function toError(res: Response): Promise<Error> {
  let detail: unknown;
  try {
    detail = (await res.json()).detail;
  } catch {
    detail = undefined;
  }

  // FastAPI/Pydantic validation failures: [{ loc: ["body", "name"], msg: "..." }]
  if (res.status === 422 && Array.isArray(detail)) {
    const fieldErrors: FieldErrors = {};
    for (const d of detail as { loc?: unknown[]; msg?: string }[]) {
      const field = d?.loc?.[1];
      if (field === "name" || field === "sourceUrl") fieldErrors[field] = d.msg ?? "Invalid value.";
    }
    if (hasErrors(fieldErrors)) return new TargetValidationError(fieldErrors);
  }
  if (res.status === 401) return new ApiError(401, "Your session has expired. Please sign in again.");
  if (res.status === 403) return new ApiError(403, "You don't have access to this target.");
  if (res.status >= 500 && res.status !== 502) return new ApiError(res.status, "The server ran into a problem. Please try again.");
  return new ApiError(res.status, typeof detail === "string" ? detail : "Something went wrong. Please try again.");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new Error("Could not reach the server. Check your connection and try again.");
  }
  if (!res.ok) throw await toError(res);
  return (res.status === 204 ? null : await res.json()) as T;
}

// ----- Mapping from backend rows to the UI shape ---------------------------

type TargetRow = {
  id: string;
  business_name?: string; // column name in Database/schema.sql
  name?: string; // column name main.py writes today
  platform?: string;
  source_url?: string;
  created_at?: string;
  ingestion_status?: IngestionStatus; // latest ingestion job, added by the backend
  ingestion_error?: string | null;
};

function toTarget(row: TargetRow): AnalysisTarget {
  return {
    id: row.id,
    name: row.business_name ?? row.name ?? "Untitled target",
    platform: PLATFORM_LABELS[row.platform ?? ""] ?? row.platform ?? TEAM_PLATFORM.label,
    sourceUrl: row.source_url ?? "",
    createdAt: row.created_at ?? new Date().toISOString(),
    // The backend reports the latest ingestion job's state. If an older backend
    // doesn't, getTarget() falls back to inferring it from stored reviews.
    ingestionStatus: row.ingestion_status ?? "not_started",
    ingestionMessage: row.ingestion_error ?? undefined,
  };
}

// ----- Stopgap for the missing "list my targets" endpoint ------------------
// Remember the ids of targets created in this browser and load each one through
// GET /api/targets/{id}, which the backend restricts to the owner. Delete this
// section once GET /api/targets exists.
const KEY = "reviewlens:target-ids";

function rememberedIds(): string[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function remember(id: string) {
  try {
    localStorage.setItem(KEY, JSON.stringify([id, ...rememberedIds().filter((x) => x !== id)].slice(0, 20)));
  } catch {
    // storage unavailable: the list just won't remember this one
  }
}

// ----- Public API used by the UI -------------------------------------------

export async function getTarget(id: string): Promise<AnalysisTarget | null> {
  let row: TargetRow;
  try {
    row = await request<TargetRow>(`/targets/${encodeURIComponent(id)}`);
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 403)) return null;
    throw err;
  }
  const target = toTarget(row);
  if (row.ingestion_status !== undefined) return target; // the backend reported the state
  try {
    const reviews = await request<unknown[]>(`/targets/${encodeURIComponent(id)}/reviews`);
    if (Array.isArray(reviews) && reviews.length > 0) target.ingestionStatus = "completed";
  } catch {
    // Reviews unavailable: leave the status as "not started".
  }
  return target;
}

export async function listTargets(): Promise<AnalysisTarget[]> {
  try {
    const rows = await request<TargetRow[]>("/targets");
    return rows.map(toTarget).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  } catch (err) {
    // 404/405 means the backend has no list endpoint yet: use the stopgap.
    if (!(err instanceof ApiError && (err.status === 404 || err.status === 405))) throw err;
  }
  const found = await Promise.all(rememberedIds().map((id) => getTarget(id).catch(() => null)));
  return found.filter((t): t is AnalysisTarget => t !== null).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function createTarget(input: NewTargetInput): Promise<AnalysisTarget> {
  const errors = validateTargetInput(input);
  if (hasErrors(errors)) throw new TargetValidationError(errors);

  const row = await request<TargetRow>("/targets", {
    method: "POST",
    body: JSON.stringify({
      name: input.name.trim(),
      platform: TEAM_PLATFORM.id, // "GOOGLE_MAPS"; the database only allows this value
      sourceUrl: input.sourceUrl.trim(),
    }),
  });
  remember(row.id);
  return toTarget(row);
}

export async function startIngestion(id: string): Promise<AnalysisTarget> {
  try {
    await request(`/targets/${encodeURIComponent(id)}/ingest`, { method: "POST" });
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 405)) {
      throw new Error("Ingestion isn't available yet: the backend doesn't have an ingest endpoint.");
    }
    throw err;
  }
  const target = await getTarget(id);
  if (!target) throw new Error("This target no longer exists.");
  return target;
}
