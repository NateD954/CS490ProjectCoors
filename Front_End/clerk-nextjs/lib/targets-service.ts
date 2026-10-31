// ---------------------------------------------------------------------------
// SERVICE BOUNDARY for AnalysisTarget. The UI only calls these four functions.
// Right now they are a mock so the UI works on its own. When the teammate's
// backend is ready, replace each body with a fetch to their endpoint and keep
// the signatures, so no component has to change. Suggested endpoints:
//   listTargets      GET  /api/targets            (only the signed-in user's)
//   createTarget     POST /api/targets            { name, sourceUrl }
//   getTarget        GET  /api/targets/:id        (404 if missing or not theirs)
//   startIngestion   POST /api/targets/:id/ingest
// For a 400 response, throw TargetValidationError with the server's field
// errors so the form can show them under the right inputs:
//   if (res.status === 400) throw new TargetValidationError((await res.json()).errors);
// ---------------------------------------------------------------------------
import { TEAM_PLATFORM } from "./config";
import type { AnalysisTarget, NewTargetInput } from "./types";
import { hasErrors, validateTargetInput, type FieldErrors } from "./validation";

export class TargetValidationError extends Error {
  fieldErrors: FieldErrors;
  constructor(fieldErrors: FieldErrors) {
    super("Some fields are invalid.");
    this.name = "TargetValidationError";
    this.fieldErrors = fieldErrors;
  }
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ----- MOCK IMPLEMENTATION (delete when the real backend is connected) -----
let store: AnalysisTarget[] = [
  {
    id: "t-1",
    name: "Sample Coffee House",
    platform: TEAM_PLATFORM.label,
    sourceUrl: "https://www.google.com/maps/place/Sample+Coffee+House",
    createdAt: "2026-10-20T12:00:00Z",
    ingestionStatus: "completed",
  },
];

export async function listTargets(): Promise<AnalysisTarget[]> {
  await wait(400);
  return [...store].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function createTarget(input: NewTargetInput): Promise<AnalysisTarget> {
  await wait(900);
  const errors = validateTargetInput(input); // stand-in for the backend's own validation
  if (hasErrors(errors)) throw new TargetValidationError(errors);
  const target: AnalysisTarget = {
    id: `t-${Date.now()}`,
    name: input.name.trim(),
    platform: TEAM_PLATFORM.label,
    sourceUrl: input.sourceUrl.trim(),
    createdAt: new Date().toISOString(),
    ingestionStatus: "not_started",
  };
  store = [target, ...store];
  return target;
}

export async function getTarget(id: string): Promise<AnalysisTarget | null> {
  await wait(300);
  return store.find((t) => t.id === id) ?? null;
}

export async function startIngestion(id: string): Promise<AnalysisTarget> {
  await wait(600);
  const target = store.find((t) => t.id === id);
  if (!target) throw new Error("This target no longer exists.");
  const running: AnalysisTarget = { ...target, ingestionStatus: "in_progress", ingestionMessage: undefined };
  store = store.map((t) => (t.id === id ? running : t));
  // Pretend the scraper finishes after a few seconds.
  setTimeout(() => {
    store = store.map((t) => (t.id === id ? { ...t, ingestionStatus: "completed" } : t));
  }, 5000);
  return running;
}
