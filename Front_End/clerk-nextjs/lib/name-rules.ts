import { MAX_NAME_LENGTH } from "./config";

// S3-002: the same name rules the backend uses (Back_End/app/analysis_names.py), for fast
// feedback while renaming. The backend is still the authority. Returns a message, or
// undefined when the name is fine.
export function validateName(raw: string): string | undefined {
  const name = raw.replace(/\s+/g, " ").trim();
  if (!name) return "Enter a name for this analysis.";
  if (name.length > MAX_NAME_LENGTH) return `Keep the name under ${MAX_NAME_LENGTH} characters.`;
  if (!/[\p{L}\p{N}]/u.test(name)) return "Use at least one letter or number in the name.";
  return undefined;
}
