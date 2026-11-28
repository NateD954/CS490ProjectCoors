import { MAX_NAME_LENGTH } from "./config";

// S3-001: a starting name for the form, taken from the place in a Google Maps link,
// e.g. ".../maps/place/Chipotle+Mexican+Grill/..." gives "Chipotle Mexican Grill".
// It is only a suggestion. The user can type any name they like. Returns "" when the
// link has no usable place name (the name is then left for the user to fill in).
export function suggestNameFromUrl(url: string): string {
  let path: string;
  try {
    path = new URL(url.trim()).pathname;
  } catch {
    return "";
  }
  const match = path.match(/\/maps\/place\/([^/]+)/);
  if (!match) return "";

  let name: string;
  try {
    name = decodeURIComponent(match[1].replace(/\+/g, " "));
  } catch {
    return ""; // a broken %-sequence in the link
  }
  name = name.replace(/\s+/g, " ").trim();

  const looksLikeCoordinates = /^[-\d.,\s]+$/.test(name);
  if (!name || looksLikeCoordinates || !/[\p{L}\p{N}]/u.test(name) || name.length > MAX_NAME_LENGTH) return "";
  return name;
}
