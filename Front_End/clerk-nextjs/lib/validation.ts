import { GOOGLE_PLACE_DATA_ID, MAX_NAME_LENGTH, TEAM_PLATFORM } from "./config";
import type { NewTargetInput } from "./types";

export type FieldErrors = Partial<Record<keyof NewTargetInput, string>>;

export const hasErrors = (e: FieldErrors) => Object.keys(e).length > 0;

// Frontend validation for fast feedback. The backend is still the authority;
// its field errors are displayed by the form too (see TargetValidationError).
export function validateTargetInput(input: NewTargetInput): FieldErrors {
  const errors: FieldErrors = {};
  const name = input.name.trim();
  const url = input.sourceUrl.trim();

  if (!name) errors.name = "Enter the business or location name.";
  else if (name.length > MAX_NAME_LENGTH) errors.name = `Keep the name under ${MAX_NAME_LENGTH} characters.`;

  if (!url) {
    errors.sourceUrl = "Enter the link to the reviews.";
  } else {
    let parsed: URL | null = null;
    try {
      parsed = new URL(url);
    } catch {
      parsed = null;
    }
    if (!parsed || (parsed.protocol !== "http:" && parsed.protocol !== "https:")) {
      errors.sourceUrl = "Enter a valid link that starts with http:// or https://.";
    } else {
      const host = parsed.hostname.toLowerCase();
      const matches = TEAM_PLATFORM.hostSuffixes.some((s) => host === s || host.endsWith(`.${s}`));
      if (!matches) {
        errors.sourceUrl = `This doesn't look like a ${TEAM_PLATFORM.label} link.`;
      } else if (!GOOGLE_PLACE_DATA_ID.test(url)) {
        errors.sourceUrl = `Use the full ${TEAM_PLATFORM.label} link for the place: open it in ${TEAM_PLATFORM.label} and copy the URL from the address bar.`;
      }
    }
  }
  return errors;
}
