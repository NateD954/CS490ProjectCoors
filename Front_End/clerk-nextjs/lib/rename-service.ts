import { validateName } from "./name-rules";

// S3-002: rename a saved analysis. Only the name changes: the source, reviews and
// Q&A history stay as they are. Resolves with the new name the server saved.
export class RenameError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RenameError";
  }
}

export async function renameTarget(id: string, name: string): Promise<string> {
  const problem = validateName(name);
  if (problem) throw new RenameError(problem); // no request for a name that is clearly unusable

  let res: Response;
  try {
    res = await fetch(`/api/backend/targets/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
      cache: "no-store",
    });
  } catch {
    throw new RenameError("Could not reach the server. Check your connection and try again.");
  }

  if (res.ok) {
    const row = await res.json();
    return row.business_name ?? row.name ?? name.trim();
  }

  let detail: unknown;
  try {
    detail = (await res.json()).detail;
  } catch {
    detail = undefined;
  }
  if (res.status === 422 && Array.isArray(detail) && detail[0]?.msg) throw new RenameError(detail[0].msg);
  if (res.status === 401) throw new RenameError("Your session has expired. Please sign in again.");
  if (res.status === 403) throw new RenameError("You don't have access to this target.");
  if (res.status === 404) throw new RenameError("This target was not found. It may have been removed.");
  if (res.status >= 500) throw new RenameError("The server ran into a problem. Please try again.");
  throw new RenameError("Could not rename this target. Please try again.");
}
