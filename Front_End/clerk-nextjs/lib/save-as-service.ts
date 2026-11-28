import { MAX_NAME_LENGTH } from "./config";
import { validateName } from "./name-rules";

// S3-003: Save As. The server makes a new analysis with its own copy of the stored reviews.
// The copy starts with an empty Q&A history. Nothing about the original changes.
export class SaveAsError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SaveAsError";
  }
}

const COPY_SUFFIX = " (copy)";

// The name the Save As form starts with. The user can change it to anything.
export function suggestCopyName(name: string): string {
  const base = name.replace(/\s+/g, " ").trim().slice(0, MAX_NAME_LENGTH - COPY_SUFFIX.length).trim();
  return `${base}${COPY_SUFFIX}`;
}

export type SavedCopy = { id: string; name: string };

export async function saveTargetAs(id: string, name: string): Promise<SavedCopy> {
  const problem = validateName(name);
  if (problem) throw new SaveAsError(problem); // no request for a name that is clearly unusable

  let res: Response;
  try {
    res = await fetch(`/api/backend/targets/${encodeURIComponent(id)}/save-as`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
      cache: "no-store",
    });
  } catch {
    throw new SaveAsError("Could not reach the server. Check your connection and try again.");
  }

  if (res.ok) {
    const row = await res.json();
    if (!row?.id) throw new SaveAsError("Could not save the copy. Please try again.");
    return { id: row.id, name: row.business_name ?? row.name ?? name.trim() };
  }

  let detail: unknown;
  try {
    detail = (await res.json()).detail;
  } catch {
    detail = undefined;
  }
  if (res.status === 422 && Array.isArray(detail) && detail[0]?.msg) throw new SaveAsError(detail[0].msg);
  if (res.status === 401) throw new SaveAsError("Your session has expired. Please sign in again.");
  if (res.status === 403) throw new SaveAsError("You don't have access to this target.");
  if (res.status === 404) throw new SaveAsError("This target was not found. It may have been removed.");
  if (res.status >= 500) throw new SaveAsError("Could not save the copy. Nothing was changed. Please try again.");
  throw new SaveAsError("Could not save the copy. Please try again.");
}
